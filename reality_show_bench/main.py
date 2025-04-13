import argparse
import json
import os
import sys
from typing import Any

import plomp

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
        "--output-dir",
        type=str,
        required=True,
        help="Path to save the HTML/JSON progress output",
    )
    parser.add_argument(
        "--existing-buffer",
        type=str,
        help="Path to an existing JSON plomp buffer if one exists",
    )
    return parser.parse_args()


def load_config(config_path: str, output_dir: str) -> Any:
    sys.stderr.write(f"Loading config from {config_path}...\n")
    sys.stderr.flush()

    with open(config_path) as f:
        config_data: dict[str, Any] = json.load(f)

    participant_configs = [
        ParticipantConfig(name=p["name"], model=p["model"], properties=p.get("properties", {}))
        for p in config_data["participants"]
    ]
    game_type = GameType[config_data["game_type"]]
    game_config = GAME_TYPE_TO_CREATE_CONFIG[game_type](participant_configs, config_data)

    sys.stderr.write(f"Creating game of type {game_type} with output to {output_dir}\n")
    sys.stderr.flush()

    return GAME_TYPE_TO_CLASS[game_type](game_config, progress_dir=output_dir), config_data


def _fill_plomp_buffer(buffer, raw_data) -> plomp.PlompBuffer:
    for item in raw_data["buffer_items"]:
        if item["type"] == "event":
            plomp.record_event(
                item["data"]["payload"],
                tags=item["tags"],
                buffer=buffer,
            )
        elif item["type"] == "prompt":
            handle = plomp.record_prompt(
                item["data"]["prompt"],
                tags=item["tags"],
                buffer=buffer,
            )
            if item.get("completion"):
                handle.complete(
                    item["completion"]["response"],
                )
        elif item["type"] == "query":
            buffer.record_query(
                plomp_query=plomp.PlompBufferQuery(
                    buffer,
                    matched_indices=item["data"]["matched_indices"],
                    op_name=item["data"]["op_name"],
                ),
                tags=item["tags"],
            )
        else:
            raise ValueError(f"Malformed input, unknown buffer item type: {item['type']!r}")


def main() -> None:
    args = parse_args()
    if args.existing_buffer:
        with open(args.existing_buffer) as f:
            existing_raw_plomp_data = json.load(f)

        _fill_plomp_buffer(plomp.buffer(), existing_raw_plomp_data)

    game, config_data = load_config(args.config, args.output_dir)

    while not game.is_finished():
        game.step()

    results: dict[str, Any] = game.get_results()

    print(
        json.dumps(
            {
                "config_name": os.path.basename(args.config),
                "config_data": config_data,
                "result": results,
            },
            indent=4,
        )
    )


if __name__ == "__main__":
    main()
