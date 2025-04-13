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
            print(f"Warning: Skipping invalid JSON file: {result_file}")
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
                role = "unknown"  # Should not happen in finished games, but handle defensively

            eliminated = name in data["result"].get("eliminated", [])
            won_prize = name in data["result"].get("prize_distribution", {})
            prize_amount = data["result"].get("prize_distribution", {}).get(name, 0)

            if eliminated:
                elimination_order = data["result"].get("eliminated", []).index(name) + 1
            else:
                # Assign a high elimination order for winners/survivors for sorting purposes if needed
                elimination_order = len(data["config_data"].get("participants", [])) + 1

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
    plt.title("Overall Win Rate by Role")
    plt.ylabel("Win Rate (%)")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(output_dir / "win_rates_by_role.png")
    plt.close()

    return win_rates


def plot_win_rates_by_model(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    model_total = df.groupby("model").size()
    model_wins = df[df["won_prize"]].groupby("model").size()
    model_win_rates = (model_wins / model_total * 100).fillna(0).sort_values(ascending=False)

    plt.figure(figsize=(10, 6))  # Increased width for potentially many models
    model_win_rates.plot(kind="bar", color="lightgreen")
    plt.title("Overall Win Rate by Model")
    plt.ylabel("Win Rate (%)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "win_rates_by_model.png")
    plt.close()

    return model_win_rates


def plot_game_outcomes(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    # Ensure we count each game only once
    game_outcomes = df.drop_duplicates("game_id")[["game_id", "winner_type"]]
    outcome_counts = game_outcomes["winner_type"].value_counts()

    plt.figure(figsize=(6, 6))
    outcome_counts.plot(kind="pie", autopct="%1.1f%%", colors=["skyblue", "salmon", "lightgreen"])
    plt.title("Game Outcomes (Winner Type)")
    plt.ylabel("")  # Hide default ylabel from pie chart
    plt.tight_layout()
    plt.savefig(output_dir / "game_outcomes.png")
    plt.close()

    return outcome_counts


def calculate_trueskill_ratings(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    # Placeholder: Simple Elo-like update for demonstration.
    # A proper TrueSkill implementation would require a library like `trueskill`
    # and consider team compositions, draws (if any), etc.
    ratings: dict[str, dict[str, float]] = {}
    init_mu = 1500  # Common starting point for Elo-like systems
    init_sigma = 350  # Initial uncertainty, adjust as needed
    k_factor = 32  # Elo K-factor, determines rating change magnitude

    for model in df["model"].unique():
        ratings[model] = {"mu": init_mu, "sigma": init_sigma}  # Sigma not used in this simple version

    for game_id in df["game_id"].unique():
        game_df = df[df["game_id"] == game_id].copy()  # Use copy to avoid SettingWithCopyWarning
        winners = game_df[game_df["won_prize"]]["model"].unique()
        losers = game_df[~game_df["won_prize"]]["model"].unique()

        # Check if either array is empty
        if winners.size == 0 or losers.size == 0:
            continue  # Skip games with no clear winners/losers for rating updates

        # Calculate average ratings for winners and losers in this game
        avg_winner_mu = sum(ratings[m]["mu"] for m in winners) / len(winners)
        avg_loser_mu = sum(ratings[m]["mu"] for m in losers) / len(losers)

        # Update ratings for each winner
        for model in winners:
            # Simplified: Each winner plays against the average loser
            expected_win = 1 / (1 + 10 ** ((avg_loser_mu - ratings[model]["mu"]) / 400))
            ratings[model]["mu"] += k_factor * (1 - expected_win)  # Actual outcome = 1 (win)

        # Update ratings for each loser
        for model in losers:
            # Simplified: Each loser plays against the average winner
            expected_win = 1 / (1 + 10 ** ((avg_winner_mu - ratings[model]["mu"]) / 400))
            ratings[model]["mu"] += k_factor * (0 - expected_win)  # Actual outcome = 0 (loss)

    # Add the 'R' value (conservative estimate) if desired, though less standard for Elo
    for model in ratings:
        ratings[model]["R"] = ratings[model]["mu"] - 3 * ratings[model]["sigma"]  # Using initial sigma here

    return ratings


def plot_trueskill_ratings(ratings: dict[str, dict[str, float]], output_dir: Path) -> pd.DataFrame:
    # Note: This plots the 'mu' value from the simplified Elo calculation
    true_skill_df = pd.DataFrame(
        {
            "model": list(ratings.keys()),
            "mu": [r["mu"] for r in ratings.values()],
            "sigma": [r["sigma"] for r in ratings.values()],  # Sigma wasn't updated in simple Elo
            "R": [r["mu"] - 3 * r["sigma"] for r in ratings.values()],
        }
    ).sort_values("mu", ascending=False)

    plt.figure(figsize=(10, 6))  # Increased width
    plt.bar(
        true_skill_df["model"],
        true_skill_df["mu"],
        yerr=true_skill_df["sigma"],
        capsize=5,
        color="orchid",
        ecolor="gray",
    )
    plt.title("Model Rating (Elo-like) based on Game Wins")
    plt.ylabel("Rating (mu)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "model_rating_elo.png")
    plt.close()

    return true_skill_df


def rank_and_plot_effective_traitors(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    traitors_df = df[df["role"] == "traitor"].copy()
    if traitors_df.empty:
        print("No traitor data found.")
        return pd.Series(dtype=float)

    traitor_total = traitors_df.groupby("model").size()
    traitor_wins = traitors_df[traitors_df["won_prize"]].groupby("model").size()

    # Calculate win rate *as a traitor*
    traitor_win_rates = (traitor_wins / traitor_total * 100).fillna(0).sort_values(ascending=False)

    plt.figure(figsize=(10, 6))
    traitor_win_rates.plot(kind="bar", color="salmon")
    plt.title("Most Effective Traitors (Win Rate as Traitor)")
    plt.ylabel("Win Rate (%)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "effective_traitors_ranking.png")
    print(f"Saved effective traitors plot to {output_dir / 'effective_traitors_ranking.png'}")
    plt.close()

    return traitor_win_rates


def rank_and_plot_successful_faithfuls(df: pd.DataFrame, output_dir: Path) -> pd.Series:
    faithfuls_df = df[df["role"] == "faithful"].copy()
    if faithfuls_df.empty:
        print("No faithful data found.")
        return pd.Series(dtype=float)

    faithful_total = faithfuls_df.groupby("model").size()
    faithful_wins = faithfuls_df[faithfuls_df["won_prize"]].groupby("model").size()

    # Calculate win rate *as a faithful*
    faithful_win_rates = (faithful_wins / faithful_total * 100).fillna(0).sort_values(ascending=False)

    plt.figure(figsize=(10, 6))
    faithful_win_rates.plot(kind="bar", color="lightseagreen")
    plt.title("Most Successful Faithfuls (Win Rate as Faithful)")
    plt.ylabel("Win Rate (%)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_dir / "successful_faithfuls_ranking.png")
    print(f"Saved successful faithfuls plot to {output_dir / 'successful_faithfuls_ranking.png'}")
    plt.close()

    return faithful_win_rates


def analyze_results(stats: list[dict[str, Any]], output_dir: str | Path) -> pd.DataFrame:
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    if not stats:
        print("No statistics extracted, cannot perform analysis.")
        return pd.DataFrame()  # Return empty DataFrame

    df = create_dataframe(stats)
    if df.empty:
        print("DataFrame is empty after creation, cannot perform analysis.")
        return df

    # --- Perform Analyses ---
    print("Generating analysis plots...")
    win_rates = plot_win_rates_by_role(df, output_dir)
    model_win_rates = plot_win_rates_by_model(df, output_dir)
    outcome_counts = plot_game_outcomes(df, output_dir)

    # Note: Using simplified Elo-like calculation instead of TrueSkill
    ratings = calculate_trueskill_ratings(df)
    model_ratings_df = plot_trueskill_ratings(ratings, output_dir)

    # Add new rankings and ensure plots are generated
    effective_traitors = rank_and_plot_effective_traitors(df, output_dir)
    successful_faithfuls = rank_and_plot_successful_faithfuls(df, output_dir)
    print("Analysis plots generated.")

    # --- Compile Summary ---
    summary = {
        "total_games_analyzed": df["game_id"].nunique(),
        "total_participants_analyzed": len(df),
        "overall_win_rates_by_role": win_rates.to_dict(),
        "overall_win_rates_by_model": model_win_rates.to_dict(),
        "game_outcomes": outcome_counts.to_dict(),
        "model_ratings_elo": model_ratings_df.set_index("model").to_dict("index"),
        "effective_traitors_win_rate": effective_traitors.to_dict(),
        "successful_faithfuls_win_rate": successful_faithfuls.to_dict(),
    }

    # --- Save Summary ---
    summary_file = output_dir / "summary_stats.json"
    try:
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=4)
        print(f"Summary statistics saved to '{summary_file}'")
    except Exception as e:
        print(f"Error saving summary statistics to '{summary_file}': {e}")

    return df


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze reality show game results.")
    parser.add_argument("--input-results-dir", type=str, required=True, help="Directory containing result.json files")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save analysis results")
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    result_files = find_result_files(args.input_results_dir)
    print(f"Found {len(result_files)} potential result files")

    stats = extract_game_stats(result_files)
    if stats:
        df = analyze_results(stats, args.output_dir)
        if not df.empty:
            print(f"Analysis complete. Results saved to '{args.output_dir}'")
            print(f"Processed data for {df['game_id'].nunique()} finished games with {len(df)} participants")
        else:
            print("Analysis could not be performed due to empty data.")
    else:
        print("No valid finished game data found in the specified directory.")


if __name__ == "__main__":
    main()
