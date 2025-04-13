import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol, runtime_checkable

# Ignore plomp import type error
import plomp  # type: ignore


class GameType(Enum):
    THE_TRAITORS = auto()


@dataclass
class Participant:
    name: str
    model: str
    active: bool
    properties: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class GameConfigProtocol(Protocol):
    participants: list[Participant]


class RealityGame(ABC):
    def __init__(self, participants: list[Participant], *, progress_dir: str | None = None):
        self.participants = participants
        self.round = 0
        self.finished = False
        self.progress_dir = progress_dir

    def _write_progress(self) -> None:
        import os

        if self.progress_dir:
            sys.stderr.write(f"Writing to: {os.path.abspath(self.progress_dir)} \n")
            sys.stderr.flush()
            plomp.write_html(plomp.buffer(), os.path.join(self.progress_dir, "plomp.html"))
            plomp.write_json(plomp.buffer(), os.path.join(self.progress_dir, "plomp.json"))

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def step(self) -> None:
        pass

    def is_finished(self) -> bool:
        return self.finished

    @abstractmethod
    def get_results(self) -> dict[str, Any]:
        pass
