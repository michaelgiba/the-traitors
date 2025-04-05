from . import _the_traitors
from ._types import GameType

GAME_TYPE_TO_CREATE_CONFIG = {
    GameType.THE_TRAITORS: _the_traitors.create_config,
}

GAME_TYPE_TO_CLASS = {GameType.THE_TRAITORS: _the_traitors.TheTraitorsGame}
