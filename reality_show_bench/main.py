import argparse
import json
from typing import Any, Dict

from reality_show_bench.config import ParticipantConfig
from reality_show_bench.games import (
    GAME_TYPE_TO_CLASS,
    GAME_TYPE_TO_CREATE_CONFIG,
    GameType,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reality Show Benchmark")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the configuration file for the game",
    )
    return parser.parse_args()


def load_config(config_path: str) -> Any:
    with open(config_path, "r") as f:
        config_data: Dict[str, Any] = json.load(f)

    participant_configs = [
        ParticipantConfig(name=p["name"], model=p["model"], properties=p.get("properties", {}))
        for p in config_data["participants"]
    ]
    game_type = GameType[config_data["game_type"]]
    game_config = GAME_TYPE_TO_CREATE_CONFIG[game_type](participant_configs, config_data)
    return GAME_TYPE_TO_CLASS[game_type](game_config, progress_uri="out.html")


def main() -> None:
    args = parse_args()
    game = load_config(args.config)
    game.start()

    while not game.is_finished():
        game.step()

    results: Dict[str, Any] = game.get_results()

    # Convert results to JSON and print to stdout
    results_json = json.dumps(results, indent=4)
    print(results_json)


if __name__ == "__main__":
    main()
