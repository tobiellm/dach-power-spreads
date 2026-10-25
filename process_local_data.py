from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.size"] = 10

FIG_DIR = Path("figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)


def load_data() -> pd.DataFrame:
    df = pd.read_parquet("processed/dach_market_data.parquet")

    df["hour"] = df.index.hour
    df["month"] = df.index.month
    df["year"] = df.index.year
    df["season"] = df["month"].map(
        lambda m: "Summer (Apr-Sep)" if 4 <= m <= 9 else "Winter (Oct-Mar)"
    )

    if "Flow_DE_LU_to_AT" in df and "Flow_AT_to_DE_LU" in df:
        df["NetFlow_DE_to_AT"] = df["Flow_DE_LU_to_AT"] - df["Flow_AT_to_DE_LU"]

    if "Flow_DE_LU_to_CH" in df and "Flow_CH_to_DE_LU" in df:
        df["NetFlow_DE_to_CH"] = df["Flow_DE_LU_to_CH"] - df["Flow_CH_to_DE_LU"]

    return df


def print_market_statistics(df: pd.DataFrame) -> None:
    spreads = [
        col for col in ["Spread_AT_DE", "Spread_CH_DE", "Spread_CH_AT"] if col in df.columns
    ]

    print("\n" + "=" * 70)
    print("      DACH POWER MARKET METRICS (SUMMARY TABLE)")
    print("=" * 70)

    stats = pd.DataFrame(index=spreads)
    stats["Mean (€/MWh)"] = df[spreads].mean().round(2)
    stats["Median (€/MWh)"] = df[spreads].median().round(2)
    stats["Std Dev (€/MWh)"] = df[spreads].std().round(2)
    stats["Max Spread (€)"] = df[spreads].max().round(2)
    stats["Min Spread (€)"] = df[spreads].min().round(2)

    stats["Convergence <0.50€ (%)"] = ((df[spreads].abs() < 0.50).mean() * 100).round(1)
    stats["Hours Zone1 > Zone2 (%)"] = ((df[spreads] > 0.50).mean() * 100).round(1)

    print(stats.to_string())
    print("=" * 70)

    print("\nNegative Price Hours:")
    for col in ["Price_DE_LU", "Price_AT", "Price_CH"]:
        if col in df.columns:
            neg_hours = int((df[col] < 0).sum())
            min_price = df[col].min()
            print(f"  - {col}: {neg_hours} hours (Min: {min_price:.2f} EUR/MWh)")

    print("\n--- COPY BELOW FOR README.MD ---")
    header = "| Metric | " + " | ".join(stats.columns) + " |"
    sep = "|---|" + "|".join(["---:"] * len(stats.columns)) + "|"
    print(header)
    print(sep)
    for idx, row in stats.iterrows():
        vals = " | ".join(f"{v}" for v in row.values)
        print(f"| **{idx}** | {vals} |")
    print("--------------------------------\n")


def plot_intraday_duck_curve(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)

    spread_configs = [
        ("Spread_AT_DE", "Austria vs. Germany (AT - DE_LU)"),
        ("Spread_CH_DE", "Switzerland vs. Germany (CH - DE_LU)"),
    ]

    for ax, (spread_col, title) in zip(axes, spread_configs):
        sns.lineplot(
            data=df,
            x="hour",
            y=spread_col,
            hue="season",
            ax=ax,
            palette=["#e66101", "#5e3c99"],
            linewidth=2.4,
            errorbar=None,
        )
        ax.axhline(0, color="gray", linestyle="--", linewidth=1.2, alpha=0.8)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel("Hour of Day (CET/CEST)")
        ax.set_ylabel("Price Spread (EUR/MWh)")
        ax.set_xticks(range(0, 24, 2))
        ax.legend(title=None)

    plt.suptitle(
        "Intraday Spread Profile: Midday Solar Compression vs. Alpine Flexibility",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()
    plot_path = FIG_DIR / "intraday_spreads.png"
    plt.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved figure: {plot_path}")


def plot_flows_vs_spread(df: pd.DataFrame) -> None:
    if "NetFlow_DE_to_AT" not in df.columns:
        return

    plot_data = df.dropna(subset=["Spread_AT_DE", "NetFlow_DE_to_AT"])
    plot_data = plot_data[plot_data["Spread_AT_DE"].between(-60, 80)]

    fig, ax = plt.subplots(figsize=(10, 6))

    scatter = ax.scatter(
        plot_data["Spread_AT_DE"],
        plot_data["NetFlow_DE_to_AT"],
        c=plot_data["hour"],
        cmap="viridis",
        alpha=0.3,
        s=12,
    )

    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("Hour of Day (CET/CEST)")

    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.axvline(0, color="black", linestyle="--", linewidth=1)

    ax.set_title(
        "Market Coupling: Price Spread vs. Physical Net Flow (DE_LU -> AT)",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Price Spread AT - DE_LU (EUR/MWh) [Right: AT more expensive than DE]")
    ax.set_ylabel("Physical Net Flow DE -> AT (MW) [Top: Net Export DE to AT]")

    plt.tight_layout()
    plot_path = FIG_DIR / "flows_vs_spread_at_de.png"
    plt.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved figure: {plot_path}")


if __name__ == "__main__":
    print("Loading Parquet dataset...")
    df = load_data()
    print_market_statistics(df)
    plot_intraday_duck_curve(df)
    plot_flows_vs_spread(df)