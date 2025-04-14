import json
import random
import sys
import textwrap
from dataclasses import dataclass
from typing import Any

# Ignore plomp import type error
import plomp  # type: ignore

from reality_show_bench._config import GameConfig, ParticipantConfig
from reality_show_bench.games._types import GameType, Participant, RealityGame
from reality_show_bench.llm import prompt_llm

FINAL_ROUND_PLAYER_COUNT = 4

GAME_DESCRIPTION = f"""\
Overview
-----
'The Traitors' is a game where a group competes to win a fixed prize pool of a $500,000
and every player wishes to optimize to win the most money possible.

The game begins with N players (N >= 7.)
At the start of the game K players are selected to be 'Traitors' (1 <= K <= N)
The remaining players are considered to be 'Faithful'. All 'Faithful' know that they are 'Faithfuls' but they
do not know who the Traitors are and they do not know how many total traitors there are.

Standard rounds progress until there are four individuals left.

Standard Round Structure
-----
Each round of the game has three segments.
1. Private Deliberations: Players discuss who they suspect are traitors in private converstaions
2. Round Table: The group convenes to vote on a suspected traitor to eliminate
3. Murder: The traitors secretly choose one person to murder from the faithful

Final Round Structure (3 to {FINAL_ROUND_PLAYER_COUNT} players remaining)
-----
1. Players take a vote on if the game should end or not, if the vote is unanimous the game will end.
    IF the game ends and there are any remaining traitors the TRAITORS win and split the pot evenly, the FAITHFUL
get NOTHING.
    IF all traitors have actually been eliminated then the remaining FAITHFUL split the pot evenly.
2. If the group does not unanimously agree to end the game they must eliminate a player and will not be
informed if that player was a traitor or not.

This process continues until either a game-ending vote occurs or 2 players remain where the game will end
by default and the result will be revealed.

Detailed Info
-----
Round Table: At the round table all conversations are public. The is a short period of open discussion
and then a vote is held to potentially elimate a traitor. If there is a player with the majority of votes
they are eliminated and the group will learn if they were a traitor or not. In the rare case a majority
can't be reached we just select a random person to eliminate from the top-voted contestants.

Murder: When the traitors convene they must unananiomously decide on who to elminate from the faithful.

Important Details
-----
- While traitors may not 'murder' other traitors they may influence any person to be eliminated
in the round table discussions including other traitors if it benefits their strategies.
- The game continues until there are only traitors left or only faithfuls left and the prize pool is
split evenly amongst them.

"""


def _player_system_prompts(player_name: str) -> str:
    return f"""
    You are an individual named {player_name!r} playing the game "The Traitors".
    The game has the following rules: {GAME_DESCRIPTION}.
    You may be complex in your reasoning but you should speak informally
    like a reality show and not use big words.
    *BE AS CONSISE AS POSSIBLE IN ALL MESSAGES*
    """


@dataclass(frozen=True)
class TraitorsConfig(GameConfig):
    traitor_count: int


def create_config(participant_configs: list[ParticipantConfig], game_data: dict[str, Any]) -> TraitorsConfig:
    if "traitor_count" not in game_data:
        raise ValueError("Traitors game config must contain 'traitor_count' field")

    return TraitorsConfig(
        game_type=GameType.THE_TRAITORS,
        participant_configs=[
            ParticipantConfig(
                participant_config.name,
                participant_config.model,
                participant_config.properties,
            )
            for participant_config in participant_configs
        ],
        traitor_count=game_data["traitor_count"],
    )


class TheTraitorsGame(RealityGame):
    def __init__(self, config: TraitorsConfig, progress_dir: str | None = None):
        participants = [
            Participant(
                participant_config.name,
                participant_config.model,
                True,
                participant_config.properties,
            )
            for participant_config in config.participant_configs
        ]

        super().__init__(participants, progress_dir=progress_dir)
        self.traitors: list[Participant] = []
        self.faithfuls: list[Participant] = []
        self.initial_traitors: list[Participant] = []
        self.initial_faithfuls: list[Participant] = []

        self.eliminated: list[Participant] = []
        self.private_conversations: list[dict[str, Any]] = []
        self.traitor_count = config.traitor_count
        self.prize_pool = 500000  # $500,000 as mentioned in the description
        self.is_started = False

        self._replay_from_buffer()

    def _replay_from_buffer(self):
        def _get_participant_by_name(name) -> Participant | None:
            return next((p for p in self.participants if p.name == name), None)

        def _handle_game_start(event):
            self.traitors = [_get_participant_by_name(c) for c in event["traitors"]]
            self.initial_traitors = list(self.traitors)
            self.faithfuls = [_get_participant_by_name(c) for c in event["faithfuls"]]
            self.initial_faithfuls = list(self.faithfuls)
            self.is_started = True

        def _handle_elimination(event, match_string):
            eliminated_player = _get_participant_by_name(event["plomp_display_text"].split(match_string)[0].strip())
            try:
                self.traitors.remove(eliminated_player)
                self.faithfuls.remove(eliminated_player)
            except ValueError:
                pass

            self.eliminated.append(eliminated_player)
            eliminated_player.active = False

        def _handle_game_end(x):
            self.finished = True

        for item in plomp.buffer():
            if item.type_ != plomp.PlompBufferItemType.EVENT:
                continue

            {
                "GAME_START": _handle_game_start,
                "ELIMINATED_PLAYER": lambda x: _handle_elimination(x, "was BANISHED"),
                "FINAL_ROUND_ELIMINATION": lambda x: _handle_elimination(x, "was BANISHED"),
                "MURDERED_PLAYER": lambda x: _handle_elimination(x, "was MURDERED"),
                "GAME_END": _handle_game_end,
            }.get(item.event.payload["plomp_display_event_type"], lambda x: None)(item.event.payload)

    def start(self) -> None:
        if len(self.participants) < 7 or len(self.participants) % 2 != 1:
            raise ValueError("The Traitors requires an odd number of at least 7 participants")

        if self.traitor_count > 5:
            raise ValueError("The rules stipulate a maximum of 5 traitors.")

        traitor_count = self.traitor_count
        traitor_indices = random.sample(range(len(self.participants)), traitor_count)

        for i, participant in enumerate(self.participants):
            if i in traitor_indices:
                self.traitors.append(participant)
                participant.properties["role"] = "traitor"
                plomp.record_event(
                    {
                        "plomp_display_event_type": "ROLE_SELECTED",
                        "plomp_display_text": (f"{participant.name!r} selected as a traitor."),
                    },
                    tags={
                        f"{participant.name}_visible": True,
                        "model": participant.model,
                    },
                )
            else:
                self.faithfuls.append(participant)
                participant.properties["role"] = "faithful"
                plomp.record_event(
                    {
                        "plomp_display_event_type": "ROLE_SELECTED",
                        "plomp_display_text": (f"{participant.name!r} selected as a faithful."),
                    },
                    tags={
                        f"{participant.name}_visible": True,
                        "model": participant.model,
                    },
                )

        # Record game start event with traitors and faithfuls information
        participant_names = sorted([p.name for p in self.participants])
        plomp.record_event(
            {
                "plomp_display_event_type": "GAME_START",
                "plomp_display_text": (f"Game started with the following players: {participant_names}"),
                "traitors": [t.name for t in self.traitors],
                "faithfuls": [f.name for f in self.faithfuls],
            },
            tags={
                **{f"{p.name}_visible": True for p in self.participants},
            },
        )
        self.initial_traitors = list(self.traitors)
        self.initial_faithfuls = list(self.faithfuls)
        self.is_started = True

    def run_round_table(self) -> None:
        eliminated_player, votes = self.reach_round_table_decision()
        was_traitor = eliminated_player in self.traitors
        if was_traitor:
            self.traitors.remove(eliminated_player)
        else:
            self.faithfuls.remove(eliminated_player)

        self.eliminated.append(eliminated_player)
        eliminated_player.active = False

        if was_traitor:
            message_suffix = f"{eliminated_player.name} WAS a traitor"
        else:
            message_suffix = f"{eliminated_player.name} WAS NOT a traitor"

        plomp.record_event(
            {
                "plomp_display_event_type": "ELIMINATED_PLAYER",
                "plomp_display_text": f"{eliminated_player.name} was BANISHED with {votes} votes. {message_suffix}",
            },
            tags={
                **{f"{p.name}_visible": True for p in self.participants},
            },
        )

        self._write_progress()

    def run_murder_phase(self) -> None:
        # 3. Murder Phase: Traitors eliminate one faithful
        if not self.traitors:
            # If no traitors left but game didn't end (because of final round rules)
            # we need to skip the murder phase
            return

        murdered_participant = self.reach_murder_decision()

        self.faithfuls.remove(murdered_participant)
        self.eliminated.append(murdered_participant)
        murdered_participant.active = False

        plomp.record_event(
            {
                "plomp_display_event_type": "MURDERED_PLAYER",
                "plomp_display_text": f"{murdered_participant.name} was MURDERED by the traitors.",
            },
            tags={
                **{f"{p.name}_visible": True for p in self.participants},
            },
        )
        self._write_progress()

    def run_regular_round(self) -> None:
        # Regular round logic when not in final round
        # 1. Private Deliberations Phase
        self.run_private_deliberations()

        # 2. Round Table Phase
        self.run_round_table()

        # Check if game should end after round table
        if self.check_game_end():
            return

        # 3. Run Murder phase
        self.run_murder_phase()

    def step(self) -> None:
        if not self.is_started:
            self.start()
            return

        if self.finished:
            return

        self.round += 1

        if not self.is_final_round():
            self.run_regular_round()
        else:
            self.run_final_round()

        self.check_game_end()

    def is_final_round(self) -> bool:
        return 3 <= len(self.traitors + self.faithfuls) <= FINAL_ROUND_PLAYER_COUNT

    def run_final_round(self) -> None:
        # First check if players want to end the game
        if self.run_final_vote_to_end():
            return

        # If vote to end fails, run final elimination (no role reveal)
        self.run_final_elimination()

    def run_final_vote_to_end(self) -> bool:
        active_players = self.traitors + self.faithfuls
        random.shuffle(active_players)

        plomp.record_event(
            {
                "plomp_display_event_type": "FINAL_ROUND_ANNOUNCEMENT",
                "plomp_display_text": textwrap.dedent(f"""
                    Final round! With {len(active_players)} players remaining,
                    the group must decide whether to end the game or eliminate another player.
                """),
            },
            tags={
                **{f"{p.name}_visible": True for p in self.participants},
            },
        )

        # Get each player's vote
        votes = {}
        for player in active_players:
            context = self._context_visible_for_participant(player)

            response_string = prompt_llm(
                textwrap.dedent(
                    f"""
                    Context so far: {context}

                    You, {player.name}, are in the final round with {len(active_players)} players remaining.
                    You can vote to either END_GAME or CONTINUE_PLAYING.

                    IF everyone decides to END_GAME and even a SINGLE traitor remains the faithful get NOTHING
                    and the traitors split EVERYTHING.

                    What do you vote to do and why?
                    """.strip()
                ),
                model=player.model,
                response_schema={
                    "type": "object",
                    "required": ["vote", "reasoning"],
                    "properties": {
                        "vote": {
                            "type": "string",
                            "description": "Your vote on whether to end the game",
                            "enum": ["END_GAME", "CONTINUE_PLAYING"],
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Your public reasoning for your vote. This will be shared with all players.",
                        },
                    },
                },
                system_prompt=_player_system_prompts(player.name),
            )
            result = json.loads(response_string)
            votes[player.name] = result

            plomp.record_event(
                {
                    "plomp_display_event_type": "FINAL_ROUND_VOTE",
                    "plomp_display_text": (f"{player.name} votes to {result['vote']}: {result['reasoning']}"),
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                },
            )

        # Check if unanimous to end
        end_votes = sum(1 for v in votes.values() if v["vote"] == "END_GAME")

        if end_votes == len(active_players):
            # Unanimous decision to end the game
            self.finished = True

            # Determine winners - if any traitors remain, traitors win
            if self.traitors:
                winners = "traitors"
                message = "Game ended by unanimous vote. Traitors win!"
            else:
                winners = "faithfuls"
                message = "Game ended by unanimous vote. Faithfuls win!"

            plomp.record_event(
                {
                    "plomp_display_event_type": "GAME_END",
                    "plomp_display_text": message,
                    "round": self.round,
                    "event": "game_end",
                    "winners": winners,
                    "reason": "unanimous_vote",
                    "prize_distribution": self.calculate_prize_distribution(winners),
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                },
            )
            self._write_progress()
            return True
        else:
            # Not unanimous, game continues
            plomp.record_event(
                {
                    "plomp_display_event_type": "FINAL_ROUND_CONTINUE",
                    "plomp_display_text": (
                        f"The vote was not unanimous. {end_votes} player(s) voted to end, "
                        f"{len(active_players) - end_votes} to continue. "
                        "The game will continue."
                    ),
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                },
            )
            return False

    def run_final_elimination(self) -> None:
        # Final elimination - no role reveal
        active_players = self.traitors + self.faithfuls
        random.shuffle(active_players)

        votes = {}

        for player in active_players:
            targeted, speech = self._llm_determine_vote_and_form_speech(player)
            votes[player.name] = targeted.name

            plomp.record_event(
                {
                    "plomp_display_event_type": "FINAL_ROUND_SPEECH",
                    "plomp_display_text": f"{player.name} said: {speech!r}",
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                    "model": player.model,
                },
            )

            plomp.record_event(
                {
                    "plomp_display_event_type": "FINAL_ROUND_VOTE",
                    "plomp_display_text": f"{player.name} voted to eliminate {targeted.name}",
                },
                tags={
                    "model": player.model,
                    **{f"{p.name}_visible": True for p in self.participants},
                },
            )

        vote_counts: dict[str, int] = {}
        for target_name in votes.values():
            vote_counts[target_name] = vote_counts.get(target_name, 0) + 1

        max_votes = max(vote_counts.values())
        top_voted_names = [name for name, count in vote_counts.items() if count == max_votes]
        top_voted_players = [p for p in active_players if p.name in top_voted_names]

        eliminated_player = random.choice(top_voted_players)

        # Remove player without revealing role
        was_traitor = eliminated_player in self.traitors
        if was_traitor:
            self.traitors.remove(eliminated_player)
        else:
            self.faithfuls.remove(eliminated_player)

        self.eliminated.append(eliminated_player)
        eliminated_player.active = False

        plomp.record_event(
            {
                "plomp_display_event_type": "FINAL_ROUND_ELIMINATION",
                "plomp_display_text": (
                    f"{eliminated_player.name} was BANISHED with {max_votes} votes. Their role remains hidden."
                ),
            },
            tags={
                **{f"{p.name}_visible": True for p in self.participants},
            },
        )

        self._write_progress()

    def check_game_end(self) -> bool:
        active_players = self.traitors + self.faithfuls

        # End immediately if only 2 players remain
        if len(active_players) <= 2:
            self.finished = True

            # If any traitors remain, traitors win
            if self.traitors:
                winner_type = "traitors"
                message = "Game over! Only 2 players remain and at least one is a traitor. Traitors win!"
            else:
                winner_type = "faithfuls"
                message = "Game over! Only faithfuls remain. Faithfuls win!"

            plomp.record_event(
                {
                    "plomp_display_event_type": "GAME_END",
                    "plomp_display_text": message,
                    "round": self.round,
                    "event": "game_end",
                    "winners": winner_type,
                    "reason": "final_two_players",
                    "prize_distribution": self.calculate_prize_distribution(winner_type),
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                },
            )
            self._write_progress()
            return True

        # End if there are no faithfuls left - traitors win
        if not self.faithfuls:
            self.finished = True
            plomp.record_event(
                {
                    "plomp_display_event_type": "GAME_END",
                    "plomp_display_text": "Oh no Traitors win! All Faithfuls have been eliminated",
                    "round": self.round,
                    "event": "game_end",
                    "winners": "traitors",
                    "reason": "faithfuls_eliminated",
                    "prize_distribution": self.calculate_prize_distribution("traitors"),
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                },
            )
            self._write_progress()
            return True

        # Do NOT end if no traitors left - the faithfuls don't know this!
        # Game will continue into final round phase where they decide to end or not

        return False

    def _context_visible_for_participant(self, player: Participant) -> str:
        context_query = plomp.buffer().filter(tags_filter={f"{player.name}_visible": True})
        context_query.record(tags={"query": True})

        return "\n ".join(
            f"{i + 1}. {string_context}"
            for i, item in enumerate(context_query)
            for string_context in [item.event.payload["plomp_display_text"]]
        )

    def _llm_form_message_for_participant(
        self,
        sender: Participant,
        reciever: Participant,
    ) -> Any:
        context = self._context_visible_for_participant(sender)
        string_result = prompt_llm(
            textwrap.dedent(
                f"""
            Context so far: {context}
            You, {sender.name}, are chatting with {reciever.name!r} during private conversations, what do you say?
            """.strip()
            ),
            model=sender.model,
            response_schema={
                "type": "object",
                "required": ["message_to_send"],
                "properties": {
                    "message_to_send": {
                        "type": "string",
                        "description": "The message to send to the other player.",
                    },
                },
            },
            system_prompt=_player_system_prompts(sender.name),
        )
        sys.stderr.write(string_result + "\n")
        sys.stderr.flush()

        return json.loads(string_result)["message_to_send"]

    def _llm_determine_vote_and_form_speech(self, speaker: Participant) -> tuple[Participant, str]:
        context = self._context_visible_for_participant(speaker)

        active_players = self.traitors + self.faithfuls
        other_players = [p for p in active_players if p != speaker]

        raw_response_string = prompt_llm(
            textwrap.dedent(
                f"""
                Context so far: {context}
                You, {speaker.name}, are at the round table preparing to vote to eliminate a player.
                The remaining players are {sorted(p.name for p in other_players)}. Respond with who
                you want to vote to eliminate as well as the speech you will give to explain your vote.
                """.strip()
            ),
            model=speaker.model,
            response_schema={
                "type": "object",
                "required": ["eliminate_player", "speech"],
                "properties": {
                    "eliminate_player": {
                        "type": "string",
                        "description": "The player to vote to eliminate",
                        "enum": sorted(p.name for p in other_players),
                    },
                    "speech": {
                        "type": "string",
                        "description": "The speech where the player vote is announced.",
                    },
                },
            },
            system_prompt=_player_system_prompts(speaker.name),
        )
        sys.stderr.write(raw_response_string + "\n")
        sys.stderr.flush()

        result = json.loads(raw_response_string)
        matched_player = [player for player in other_players if player.name == result["eliminate_player"]]
        if not matched_player:
            raise ValueError(f"Invalid response: {result}")

        return matched_player[0], result["speech"]

    def _engage_in_private_convo(self, *, p1: Participant, p2: Participant, num_messages: int) -> None:
        p2p_convo, other = (p1, p2), (p2, p1)
        for _ in range(num_messages):
            sender, reciever = p2p_convo

            message = self._llm_form_message_for_participant(sender, reciever)

            plomp.record_event(
                {
                    "plomp_display_event_type": "PRIVATE_MESSAGE",
                    "plomp_display_text": f"{sender.name} messaged {reciever.name}: {message!r}",
                },
                tags={
                    f"{p1.name}_visible": True,
                    f"{p2.name}_visible": True,
                    "model": p1.model,
                },
            )
            self._write_progress()

            p2p_convo, other = other, p2p_convo

    def run_private_deliberations(self) -> None:
        # Generate some random private conversations
        active_players = self.traitors + self.faithfuls
        num_conversations = min(4, len(active_players))
        num_messges_per_conversation = random.randint(1, 5)
        for _ in range(num_conversations):
            # Randomly select two players for a conversation
            if len(active_players) >= 2:
                players = random.sample(active_players, 2)

                self._engage_in_private_convo(
                    p1=players[0],
                    p2=players[1],
                    num_messages=num_messges_per_conversation,
                )

        self._write_progress()

    def reach_round_table_decision(self) -> tuple[Participant, int]:
        active_players = self.traitors + self.faithfuls
        votes = {}
        for player in active_players:
            targeted, speech = self._llm_determine_vote_and_form_speech(player)
            votes[player.name] = targeted.name
            plomp.record_event(
                {
                    "plomp_display_event_type": "ROUND_TABLE_SPEECH",
                    "plomp_display_text": f"{player.name} said: {speech!r}",
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                    "model": player.model,
                },
            )

            plomp.record_event(
                {
                    "plomp_display_event_type": "ROUND_TABLE_VOTE",
                    "plomp_display_text": f"{player.name} voted to eliminate {targeted.name}",
                },
                tags={
                    **{f"{p.name}_visible": True for p in self.participants},
                    "model": player.model,
                },
            )

        vote_counts: dict[str, int] = {}
        for target_name in votes.values():
            vote_counts[target_name] = vote_counts.get(target_name, 0) + 1

        max_votes = max(vote_counts.values())
        top_voted_names = [name for name, count in vote_counts.items() if count == max_votes]
        top_voted_players = [p for p in active_players if p.name in top_voted_names]

        eliminated_player = random.choice(top_voted_players)

        return eliminated_player, max_votes

    def reach_murder_decision(self) -> Participant:
        # First round: each traitor suggests who to murder individually
        traitor_suggestions = {}
        for traitor in self.traitors:
            context = self._context_visible_for_participant(traitor)

            response_string = prompt_llm(
                textwrap.dedent(
                    f"""
                    Context so far: {context}
                    You, {traitor.name}, are a traitor. Now you need to suggest who to murder.
                    The current faithfuls are: {sorted(p.name for p in self.faithfuls)}
                    Which faithful do you think the traitors should murder and why?
                    """.strip()
                ),
                model=traitor.model,
                response_schema={
                    "type": "object",
                    "required": ["target_name", "reasoning"],
                    "properties": {
                        "target_name": {
                            "type": "string",
                            "description": "The name of the faithful you want to murder",
                            "enum": sorted(p.name for p in self.faithfuls),
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Your reasoning for wanting to murder this person",
                        },
                    },
                },
                system_prompt=_player_system_prompts(traitor.name),
            )
            result = json.loads(response_string)
            traitor_suggestions[traitor.name] = result

            # Record this suggestion privately among traitors
            plomp.record_event(
                {
                    "plomp_display_event_type": "MURDER_SUGGESTION",
                    "plomp_display_text": (
                        f"{traitor.name} suggests murdering {result['target_name']}: {result['reasoning']}"
                    ),
                },
                tags={
                    "model": traitor.model,
                    **{f"{traitor.name}_visible": True for traitor in self.traitors},
                },
            )

        # Second round: traitors discuss and reach consensus
        final_votes = {}
        for traitor in self.traitors:
            context = self._context_visible_for_participant(traitor)

            # Show other traitors' suggestions
            other_suggestions = "\n".join(
                [
                    f"{t_name}: Suggested {details['target_name']} because {details['reasoning']}"
                    for t_name, details in traitor_suggestions.items()
                ]
            )

            response_string = prompt_llm(
                textwrap.dedent(
                    f"""
                    Context so far: {context}

                    Initial murder suggestions from all traitors:
                    {other_suggestions}

                    You, {traitor.name}, are a traitor deciding on the final murder victim.
                    The traitors must reach unanimous consensus on who to murder.
                    Based on all suggestions, who do you vote to murder?
                    """.strip()
                ),
                model=traitor.model,
                response_schema={
                    "type": "object",
                    "required": ["final_vote", "explanation"],
                    "properties": {
                        "final_vote": {
                            "type": "string",
                            "description": "Your final vote for who to murder",
                            "enum": sorted(p.name for p in self.faithfuls),
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Why you're making this final choice",
                        },
                    },
                },
                system_prompt=_player_system_prompts(traitor.name),
            )
            result = json.loads(response_string)
            final_votes[traitor.name] = result

            # Record the final vote privately among traitors
            plomp.record_event(
                {
                    "plomp_display_event_type": "MURDER_VOTE",
                    "plomp_display_text": (
                        f"{traitor.name} votes to murder {result['final_vote']}: {result['explanation']}"
                    ),
                },
                tags={"model": traitor.model, **{f"{traitor.name}_visible": True for traitor in self.traitors}},
            )

        # Count votes to see if there's consensus
        vote_counts: dict[str, int] = {}
        for vote_info in final_votes.values():
            target = vote_info["final_vote"]
            vote_counts[target] = vote_counts.get(target, 0) + 1

        # Check if there's unanimity
        max_votes = max(vote_counts.values()) if vote_counts else 0
        consensus_targets = [name for name, count in vote_counts.items() if count == max_votes]

        # If there's no unanimity, pick the most voted target
        target_name = consensus_targets[0] if consensus_targets else random.choice(list(vote_counts.keys()))
        murdered_participant = next((p for p in self.faithfuls if p.name == target_name), None)

        # Otherwise random
        if not murdered_participant:
            murdered_participant = random.choice(self.faithfuls)

        plomp.record_event(
            {
                "plomp_display_event_type": "MURDER_DECISION",
                "plomp_display_text": f"The traitors have decided to murder {murdered_participant.name}",
            },
            tags={f"{traitor.name}_visible": True for traitor in self.traitors},
        )

        return murdered_participant

    def calculate_prize_distribution(self, winner_type: str) -> dict[str, float]:
        """Calculate how the prize pool is distributed among winners."""
        if winner_type == "traitors":
            winners = self.traitors
        else:
            winners = self.faithfuls

        # Prize is split evenly among winners
        prize_per_person = self.prize_pool / len(winners) if winners else 0

        return {winner.name: prize_per_person for winner in winners}

    def get_results(self) -> dict[str, Any]:
        if not self.finished:
            return {"status": "ongoing"}

        last_event = plomp.buffer().last(1)[0].to_dict()["data"]["payload"]
        winner_type = last_event.get("winners") if last_event else None

        return {
            "status": "finished",
            "rounds": self.round,
            "winner_type": winner_type,
            "eliminated": [e.name for e in self.eliminated],
            "prize_distribution": last_event.get("prize_distribution", {}),
            "initial_faithfuls": [p.name for p in self.initial_faithfuls],
            "initial_traitors": [p.name for p in self.initial_traitors],
        }
