from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reality_show_bench.games import GameType


@dataclass(frozen=True)
class ParticipantConfig:
    name: str
    model: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GameConfig:
    game_type: "GameType"
    participant_configs: list[ParticipantConfig]

    def __post_init__(self) -> None:
        from reality_show_bench.games import GameType

        if isinstance(self.game_type, str):
            object.__setattr__(self, "game_type", GameType(self.game_type))
