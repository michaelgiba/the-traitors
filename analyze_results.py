import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def find_result_files(base_dir):
    result_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file == "result.json":
                result_files.append(os.path.join(root, file))
    return result_files


def load_result_data(file_path):
    with open(file_path, "r") as f:
        return json.load(f)


def extract_game_stats(results):
    stats = []

    for result_file in results:
        try:
            data = load_result_data(result_file)
        except json.decoder.JSONDecodeError:
            continue
        # Skip if result is not finished
        if data.get("result", {}).get("status") != "finished":
            continue

        game_id = os.path.basename(os.path.dirname(result_file))
        game_stats = {
            "game_id": game_id,
            "winner_type": data["result"].get("winner_type", "unknown"),
            "rounds": data["result"].get("rounds", 0),
            "participants": len(data["config_data"].get("participants", [])),
            "traitor_count": data["config_data"].get("traitor_count", 0),
        }

        # Extract participant details
        for p in data["config_data"].get("participants", []):
            name = p["name"]
            model = p["model"]

            # Determine role from initial_faithfuls/initial_traitors lists
            if name in data["result"].get("initial_traitors", []):
                role = "traitor"
            elif name in data["result"].get("initial_faithfuls", []):
                role = "faithful"
            else:
                role = "unknown"

            # Check if participant was eliminated
            eliminated = name in data["result"].get("eliminated", [])

            # Check if participant won prize money
            won_prize = name in data["result"].get("prize_distribution", {})
            prize_amount = data["result"].get("prize_distribution", {}).get(name, 0)

            # Get elimination order if eliminated
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
                "winner_type": data["result"].get("winner_type", "unknown"),  # added field
            }
            stats.append(participant_stats)

    return stats


def analyze_results(stats):
    df = pd.DataFrame(stats)

    output_dir = Path("/home/michaelgiba/code/github/reality-show-bench/analysis")
    output_dir.mkdir(exist_ok=True)

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

    model_total = df.groupby("model").size()
    model_wins = df[df["won_prize"]].groupby("model").size()
    model_win_rates = (model_wins / model_total * 100).fillna(0).sort_values(ascending=False)

    plt.figure(figsize=(8, 6))
    model_win_rates.plot(kind="bar", color="lightgreen")
    plt.title("Win Rate by Model")
    plt.ylabel("Win Rate (%)")
    plt.tight_layout()
    plt.savefig(output_dir / "win_rates_by_model.png")
    plt.close()

    game_outcomes = df.drop_duplicates("game_id")[["game_id", "winner_type"]]
    outcome_counts = game_outcomes["winner_type"].value_counts()

    plt.figure(figsize=(6, 6))
    outcome_counts.plot(kind="pie", autopct="%1.1f%%", colors=["skyblue", "salmon", "lightgreen"])
    plt.title("Game Outcomes")
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(output_dir / "game_outcomes.png")
    plt.close()

    summary = {
        "total_games": df["game_id"].nunique(),
        "win_rates": win_rates.to_dict(),
        "model_win_rates": model_win_rates.to_dict(),
        "game_outcomes": outcome_counts.to_dict(),
    }

    # Updated TrueSkill visualization using manual calculations
    ratings = {}
    init_mu = 25
    init_sigma = 25 / 3
    for model in df["model"].unique():
        ratings[model] = {"mu": init_mu, "sigma": init_sigma}
    for game in df["game_id"].unique():
        game_df = df[df["game_id"] == game]
        winners = list(game_df[game_df["won_prize"] == True]["model"].unique())
        losers = list(game_df[game_df["won_prize"] == False]["model"].unique())
        if winners and losers:
            avg_winner_R = sum(ratings[m]["mu"] - 3 * ratings[m]["sigma"] for m in winners) / len(winners)
            avg_loser_R = sum(ratings[m]["mu"] - 3 * ratings[m]["sigma"] for m in losers) / len(losers)
            for m in winners:
                R = ratings[m]["mu"] - 3 * ratings[m]["sigma"]
                delta = 0.1 * (avg_loser_R - R)
                ratings[m]["mu"] += delta
                ratings[m]["sigma"] *= 0.95
            for m in losers:
                R = ratings[m]["mu"] - 3 * ratings[m]["sigma"]
                delta = 0.1 * (R - avg_winner_R)
                ratings[m]["mu"] -= delta
                ratings[m]["sigma"] *= 1.05
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

    summary["trueskill"] = true_skill_df.set_index("model").to_dict("index")

    with open(output_dir / "summary_stats.json", "w") as f:
        json.dump(summary, f, indent=4)

    return df


if __name__ == "__main__":
    results_dir = "/home/michaelgiba/code/github/reality-show-bench/results"
    result_files = find_result_files(results_dir)
    print(f"Found {len(result_files)} result files")

    stats = extract_game_stats(result_files)
    if stats:
        df = analyze_results(stats)
        print("Analysis complete. Results saved to '/home/michaelgiba/code/github/reality-show-bench/analysis'")
        print(f"Processed data for {len(df['game_id'].unique())} games with {len(df)} participants")
    else:
        print("No valid result data found")
