import argparse
import json
import os
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


def find_result_files(base_dir: str) -> list[str]:
    result_files: list[str] = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file == "result.json":
                result_files.append(os.path.join(root, file))
    return result_files


def load_result_data(file_path: str) -> Any:
    with open(file_path) as f:
        return json.load(f)


def extract_game_stats(results: list[str]) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []

    for result_file in results:
        try:
            data = load_result_data(result_file)
        except json.decoder.JSONDecodeError:
            continue

        if data.get("result", {}).get("status") != "finished":
            continue

        game_id = os.path.basename(os.path.dirname(result_file))

        for p in data["config_data"].get("participants", []):
            name = p["name"]
            model = p["model"]

            if name in data["result"].get("initial_traitors", []):
                role = "traitor"
            elif name in data["result"].get("initial_faithfuls", []):
                role = "faithful"
            else:
                role = "unknown"

            eliminated = name in data["result"].get("eliminated", [])
            won_prize = name in data["result"].get("prize_distribution", {})
            prize_amount = data["result"].get("prize_distribution", {}).get(name, 0)

            if eliminated:
                elimination_order = data["result"].get("eliminated", []).index(name) + 1
            else:
                elimination_order = None

            participant_stats = {
                "game_id": game_id,
                "name": name,
                "model": model,
                "role": role,
                "eliminated": eliminated,
                "elimination_order": elimination_order,
                "won_prize": won_prize,
                "prize_amount": prize_amount,
                "winner_type": data["result"].get("winner_type", "unknown"),
            }
            stats.append(participant_stats)

    return stats


def create_dataframe(stats: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(stats)


def plot_win_rates_by_role(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    role_total = df.groupby("role").size()
    role_wins = df[df["won_prize"]].groupby("role").size()
    win_rates = (role_wins / role_total * 100).fillna(0).sort_values(ascending=False)

    plt.figure(figsize=(8, 6))
    win_rates.plot(kind="bar", color="skyblue")
    plt.title("Win Rate by Role")
    plt.ylabel("Win Rate (%)")
    plt.tight_layout()
    plt.savefig(output_dir / "win_rates_by_role.png")
    plt.close()

    return win_rates


def plot_win_rates_by_model(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    model_total = df.groupby("model").size()
    model_wins = df[df["won_prize"]].groupby("model").size()
    model_win_rates = (model_wins / model_total * 100).fillna(0).sort_values(ascending=False)

    plt.figure(figsize=(8, 6))
    model_win_rates.plot(kind="bar", color="lightgreen")
    plt.title("Win Rate by Model")
    plt.ylabel("Win Rate (%)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "win_rates_by_model.png")
    plt.close()

    return model_win_rates


def plot_game_outcomes(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    game_outcomes = df.drop_duplicates("game_id")[["game_id", "winner_type"]]
    outcome_counts = game_outcomes["winner_type"].value_counts()

    plt.figure(figsize=(6, 6))
    outcome_counts.plot(kind="pie", autopct="%1.1f%%", colors=["skyblue", "salmon", "lightgreen"])
    plt.title("Game Outcomes")
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(output_dir / "game_outcomes.png")
    plt.close()

    return outcome_counts


def calculate_trueskill_ratings(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    ratings: dict[str, dict[str, float]] = {}
    init_mu = 25
    init_sigma = 25 / 3

    for model in df["model"].unique():
        ratings[model] = {"mu": init_mu, "sigma": init_sigma}

    for game in df["game_id"].unique():
        game_df = df[df["game_id"] == game]
        winners = list(game_df[game_df["won_prize"]]["model"].unique())
        losers = list(game_df[~game_df["won_prize"]]["model"].unique())

        if winners and losers:
            avg_winner_r = sum(ratings[m]["mu"] - 3 * ratings[m]["sigma"] for m in winners) / len(winners)
            avg_loser_r = sum(ratings[m]["mu"] - 3 * ratings[m]["sigma"] for m in losers) / len(losers)

            for m in winners:
                r = ratings[m]["mu"] - 3 * ratings[m]["sigma"]
                delta = 0.1 * (avg_loser_r - r)
                ratings[m]["mu"] += delta
                ratings[m]["sigma"] *= 0.95

            for m in losers:
                r = ratings[m]["mu"] - 3 * ratings[m]["sigma"]
                delta = 0.1 * (r - avg_winner_r)
                ratings[m]["mu"] -= delta
                ratings[m]["sigma"] *= 1.05

    return ratings


def plot_trueskill_ratings(ratings: dict[str, dict[str, float]], output_dir: Path) -> pd.DataFrame:
    true_skill_df = pd.DataFrame(
        {
            "model": list(ratings.keys()),
            "mu": [r["mu"] for r in ratings.values()],
            "sigma": [r["sigma"] for r in ratings.values()],
            "R": [r["mu"] - 3 * r["sigma"] for r in ratings.values()],
        }
    ).sort_values("mu", ascending=False)

    plt.figure(figsize=(8, 6))
    plt.bar(true_skill_df["model"], true_skill_df["mu"], color="orchid")
    plt.title("TrueSkill Rating by Model")
    plt.ylabel("Rating (mu)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "trueskill_by_model.png")
    plt.close()

    return true_skill_df


def analyze_results(stats: list[dict[str, Any]], output_dir: str | Path) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    df = create_dataframe(stats)

    win_rates = plot_win_rates_by_role(df, output_dir)
    model_win_rates = plot_win_rates_by_model(df, output_dir)
    outcome_counts = plot_game_outcomes(df, output_dir)

    ratings = calculate_trueskill_ratings(df)
    true_skill_df = plot_trueskill_ratings(ratings, output_dir)

    summary = {
        "total_games": df["game_id"].nunique(),
        "win_rates": win_rates.to_dict(),
        "model_win_rates": model_win_rates.to_dict(),
        "game_outcomes": outcome_counts.to_dict(),
        "trueskill": true_skill_df.set_index("model").to_dict("index"),
    }

    with open(output_dir / "summary_stats.json", "w") as f:
        json.dump(summary, f, indent=4)

    return df


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze reality show game results.")
    parser.add_argument("--input-results-dir", type=str, required=True, help="Directory containing result.json files")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save analysis results")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    result_files = find_result_files(args.input_results_dir)
    print(f"Found {len(result_files)} result files")

    stats = extract_game_stats(result_files)
    if stats:
        df = analyze_results(stats, args.output_dir)
        print(f"Analysis complete. Results saved to '{args.output_dir}'")
        print(f"Processed data for {len(df['game_id'].unique())} games with {len(df)} participants")
    else:
        print("No valid result data found")


if __name__ == "__main__":
    main()
