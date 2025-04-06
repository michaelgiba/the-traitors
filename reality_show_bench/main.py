import argparse
import json
import sys
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
    parser.add_argument(
        "--output-html",
        type=str,
        required=True,
        help="Path to save the HTML progress output",
    )
    return parser.parse_args()


def load_config(config_path: str, output_path: str) -> Any:
    sys.stderr.write(f"Loading config from {config_path}...\n")
    sys.stderr.flush()

    with open(config_path, "r") as f:
        config_data: Dict[str, Any] = json.load(f)

    participant_configs = [
        ParticipantConfig(name=p["name"], model=p["model"], properties=p.get("properties", {}))
        for p in config_data["participants"]
    ]
    game_type = GameType[config_data["game_type"]]
    game_config = GAME_TYPE_TO_CREATE_CONFIG[game_type](participant_configs, config_data)

    sys.stderr.write(f"Creating game of type {game_type} with output to {output_path}\n")
    sys.stderr.flush()

    return GAME_TYPE_TO_CLASS[game_type](game_config, progress_uri=output_path)


def main() -> None:
    args = parse_args()
    game = load_config(args.config, args.output_html)

    game.start()

    while not game.is_finished():
        game.step()

    results: Dict[str, Any] = game.get_results()

    results_json = json.dumps(results, indent=4)
    print(results_json)


if __name__ == "__main__":
    main()
