from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# Ignore plomp import type error
import plomp  # type: ignore


class GameType(Enum):
    THE_TRAITORS = auto()


@dataclass
class Participant:
    name: str
    model: str
    active: bool
    properties: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class GameConfigProtocol(Protocol):
    participants: List[Participant]


class RealityGame(ABC):
    def __init__(self, participants: List[Participant], *, progress_uri: Optional[str] = None):
        self.participants = participants
        self.round = 0
        self.finished = False
        self.progress_uri = progress_uri

    def _write_progress(self) -> None:
        if self.progress_uri:
            plomp.write_html(plomp.buffer(), self.progress_uri)

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def step(self) -> None:
        pass

    def is_finished(self) -> bool:
        return self.finished

    @abstractmethod
    def get_results(self) -> Dict[str, Any]:
        pass
