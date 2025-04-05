import random
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# Ignore plomp import type error
import plomp  # type: ignore

from reality_show_bench.config import GameConfig, ParticipantConfig
from reality_show_bench.games._types import GameType, Participant, RealityGame
from reality_show_bench.llm import prompt_llm

GAME_DESCRIPTION = """\
Overview
-----
'The Traitors' is a game where a group competes to win a fixed prize pool of a $500,000
and every player wishes to optimize to win the most money possible.

The game begins with N players (N >= 10.)
At the start of the game K players are selected to be 'Traitors' (K <= 5)
The remaining players are considered to be 'Faithful'. All 'Faithful' know that they are 'Faithfuls' but they
do not know who the Traitors are and they do not know how many total traitors there are.

Round Structure
-----
Each round of the game has three segments.
1. Private Deliberations: Players discuss who they suspect are traitors in private converstaions
2. Round Table: The group convenes to vote on a suspected traitor to eliminate
3. Murder: The traitors secretly choose one person to murder from the faithful

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
    The game has the following rules: {GAME_DESCRIPTION}
    """


@dataclass(frozen=True)
class TraitorsConfig(GameConfig):
    traitor_count: int


def create_config(participant_configs: List[ParticipantConfig], game_data: Dict[str, Any]) -> TraitorsConfig:
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
    def __init__(self, config: TraitorsConfig, progress_uri: Optional[str] = None):
        participants = [
            Participant(
                participant_config.name,
                participant_config.model,
                True,
                participant_config.properties,
            )
            for participant_config in config.participant_configs
        ]

        super().__init__(participants, progress_uri=progress_uri)
        self.traitors: List[Participant] = []
        self.faithfuls: List[Participant] = []
        self.eliminated: List[Participant] = []
        self.private_conversations: List[Dict[str, Any]] = []
        self.traitor_count = config.traitor_count
        self.prize_pool = 500000  # $500,000 as mentioned in the description

    def start(self) -> None:
        if len(self.participants) < 10:
            raise ValueError("The Traitors requires at least 10 participants")

        # Select traitors (up to 5 as per rules)
        traitor_count = min(self.traitor_count, 5)
        traitor_indices = random.sample(range(len(self.participants)), traitor_count)

        for i, participant in enumerate(self.participants):
            if i in traitor_indices:
                self.traitors.append(participant)
                participant.properties["role"] = "traitor"
                plomp.record_event(
                    {
                        "plomp_display_event_type": "role_selected",
                        "plomp_display_text": (f"{participant.name!r} selected as a traitor."),
                    },
                    tags={
                        "visibility": "private",
                        f"{participant.name}_visible": True,
                    },
                )
            else:
                self.faithfuls.append(participant)
                participant.properties["role"] = "faithful"
                plomp.record_event(
                    {
                        "plomp_display_event_type": "role_selected",
                        "plomp_display_text": (f"{participant.name!r} selected as a faithful."),
                    },
                    tags={
                        "visibility": "private",
                        f"{participant.name}_visible": True,
                    },
                )

        # Record game start event with traitors and faithfuls information
        participant_names = sorted([p.name for p in self.participants])
        plomp.record_event(
            {
                "plomp_display_event_type": "game_start",
                "plomp_display_text": (f"Game started with the following players: {participant_names}"),
                "traitors": [t.name for t in self.traitors],
                "faithfuls": [f.name for f in self.faithfuls],
            },
            tags={
                "visibility": "public",
            },
        )

    def step(self) -> None:
        if self.finished:
            return

        self.round += 1

        # 1. Private Deliberations Phase
        self.run_private_deliberations()
        self._write_progress()

        # 2. Round Table Phase
        eliminated_player, votes = self.run_round_table()
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
                "plomp_display_event_type": "eliminated_player",
                "plomp_display_text": f"{eliminated_player.name} was BANISHED with {votes} votes. {message_suffix}",
            },
            tags={
                "visibility": "public",
            },
        )

        self._write_progress()

        # Check if game should end after round table
        if self.check_game_end():
            return

        # 3. Murder Phase: Traitors eliminate one faithful
        murdered_participant = self.run_murder_phase()

        self.faithfuls.remove(murdered_participant)
        self.eliminated.append(murdered_participant)
        murdered_participant.active = False

        plomp.record_event(
            {
                "plomp_display_event_type": "murdered_player",
                "plomp_display_text": f"{murdered_participant.name} was MURDERED by the traitors.",
            },
            tags={
                "visibility": "public",
            },
        )

        self._write_progress()
        self.check_game_end()

    def _context_visible_for_participant(self, player: Participant) -> str:
        context_query = (
            plomp.buffer()
            .filter(tags_filter={f"{player.name}_visible": True, "visibility": "private"}, how="all")
            .union(plomp.buffer().filter(tags_filter={"visibility": "public"}))
        )
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
    ) -> str:
        context = self._context_visible_for_participant(sender)

        return str(
            prompt_llm(
                textwrap.dedent(
                    f"""
                You, {sender.name}, are chatting with {reciever.name!r} during private conversations, what do you say?
                Context so far: {context}""".strip()
                ),
                model=sender.model,
                response_schema={
                    "message_to_send": "string",
                },
                system_prompt=_player_system_prompts(sender.name),
            )
        )

    def _llm_determine_vote_and_form_speech(self, speaker: Participant) -> tuple[Participant, str]:
        context = self._context_visible_for_participant(speaker)

        active_players = self.traitors + self.faithfuls
        other_players = [p for p in active_players if p != speaker]

        _ = prompt_llm(
            textwrap.dedent(
                f"""
                You, {speaker.name}, are at the round table preparing to vote to eliminate a player.
                Context so far: {context}
                The remaining players are {sorted(p.name for p in other_players)}. Respond with who
                you want to vote to eliminate as well as the speech you will give to explain your vote.
                """.strip()
            ),
            model=speaker.model,
            response_schema={
                "eliminate_player": "string",
                "speech": "string",
            },
            system_prompt=_player_system_prompts(speaker.name),
        )

        return random.choice(other_players), "cuz I wana"

    def _engage_in_private_convo(self, *, p1: Participant, p2: Participant, num_messages: int) -> None:
        p2p_convo, other = (p1, p2), (p2, p1)
        for _ in range(num_messages):
            sender, reciever = p2p_convo

            message = self._llm_form_message_for_participant(sender, reciever)

            plomp.record_event(
                {
                    "plomp_display_event_type": "private_message",
                    "plomp_display_text": f"{sender.name} messaged {reciever.name}: {message[:100]!r}",
                },
                tags={
                    "visibility": "private",
                    f"{p1.name}_visible": True,
                    f"{p2.name}_visible": True,
                },
            )

            p2p_convo, other = other, p2p_convo

    def run_private_deliberations(self) -> None:
        # Generate some random private conversations
        active_players = self.traitors + self.faithfuls
        num_conversations = min(5, len(active_players))
        num_messges_per_conversation = 3
        for _ in range(num_conversations):
            # Randomly select two players for a conversation
            if len(active_players) >= 2:
                players = random.sample(active_players, 2)

                self._engage_in_private_convo(
                    p1=players[0],
                    p2=players[1],
                    num_messages=num_messges_per_conversation,
                )

    def run_round_table(self) -> Tuple[Participant, int]:
        active_players = self.traitors + self.faithfuls
        votes = {}
        for player in active_players:
            targeted, speech = self._llm_determine_vote_and_form_speech(player)
            votes[player.name] = targeted.name
            plomp.record_event(
                {
                    "plomp_display_event_type": "round_table_speech",
                    "plomp_display_text": f"{player.name} said: {speech!r}",
                },
                tags={
                    "visibility": "public",
                },
            )

            plomp.record_event(
                {
                    "plomp_display_event_type": "round_table_vote",
                    "plomp_display_text": f"{player.name} voted to eliminate {targeted.name}",
                },
                tags={
                    "visibility": "public",
                },
            )

        vote_counts: Dict[str, int] = {}
        for target_name in votes.values():
            vote_counts[target_name] = vote_counts.get(target_name, 0) + 1

        max_votes = max(vote_counts.values())
        top_voted_names = [name for name, count in vote_counts.items() if count == max_votes]
        top_voted_players = [p for p in active_players if p.name in top_voted_names]

        eliminated_player = random.choice(top_voted_players)

        return eliminated_player, max_votes

    def run_murder_phase(self) -> Participant:
        """
        Run the murder phase where traitors unanimously decide who to eliminate.
        Returns the murdered player and discussion if successful.
        """

        # For now, just randomly select a faithful to murder
        target = random.choice(self.faithfuls)

        return target

    def check_game_end(self) -> bool:
        """Check if the game should end and update state accordingly."""
        # Game ends if there are no traitors left
        if not self.traitors:
            self.finished = True
            plomp.record_event(
                {
                    "plomp_display_event_type": "game_end",
                    "plomp_display_text": "Faithfuls win! All Traitors have been eliminated",
                    "round": self.round,
                    "event": "game_end",
                    "winners": "faithfuls",
                    "reason": "traitors_eliminated",
                    "prize_distribution": self.calculate_prize_distribution("faithfuls"),
                },
                tags={
                    "visibility": "public",
                },
            )
            self._write_progress()

            return True

        # Game ends if there are no faithfuls left
        elif not self.faithfuls:
            self.finished = True
            plomp.record_event(
                {
                    "plomp_display_event_type": "game_end",
                    "plomp_display_text": "Oh no Traitors win! All Faithfuls have been eliminated",
                    "round": self.round,
                    "event": "game_end",
                    "winners": "traitors",
                    "reason": "faithfuls_eliminated",
                    "prize_distribution": self.calculate_prize_distribution("traitors"),
                },
                tags={
                    "visibility": "public",
                },
            )
            self._write_progress()

            return True

        return False

    def calculate_prize_distribution(self, winner_type: str) -> Dict[str, float]:
        """Calculate how the prize pool is distributed among winners."""
        if winner_type == "traitors":
            winners = self.traitors
        else:
            winners = self.faithfuls

        # Prize is split evenly among winners
        prize_per_person = self.prize_pool / len(winners) if winners else 0

        return {winner.name: prize_per_person for winner in winners}

    def get_results(self) -> Dict[str, Any]:
        if not self.finished:
            return {"status": "ongoing"}

        last_event = plomp.buffer().last(1)[0].to_dict()["data"]["payload"]
        winner_type = last_event.get("winners") if last_event else None

        if winner_type == "traitors":
            winners = [t.name for t in self.traitors]
        elif winner_type == "faithfuls":
            winners = [f.name for f in self.faithfuls]
        else:
            winners = []

        return {
            "status": "finished",
            "rounds": self.round,
            "winner_type": winner_type,
            "winners": winners,
            "eliminated": [e.name for e in self.eliminated],
            "prize_distribution": last_event.get("prize_distribution", {}),
        }
