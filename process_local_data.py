import glob
from pathlib import Path
import pandas as pd

ZONES = ["DE_LU", "AT", "CH"]

def load_and_filter_prices(folder_path: str) -> pd.DataFrame:
    files = sorted(glob.glob(f"{folder_path}/**/*.csv", recursive=True))
    if not files:
        raise FileNotFoundError(f"No price files found in '{folder_path}'.")

    df_list = []
    for f in files:
        df = pd.read_csv(
            f,
            sep="\t",
            usecols=[
                "DateTime(UTC)",
                "AreaMapCode",
                "Price[Currency/MWh]",
                "ContractType",
            ],
            low_memory=False,
        )

        mask = (df["AreaMapCode"].isin(ZONES)) & (
            df["ContractType"].str.lower().str.contains("day-ahead", na=False)
        )
        df_filtered = df[mask].copy()

        df_list.append(
            df_filtered[
                ["DateTime(UTC)", "AreaMapCode", "Price[Currency/MWh]"]
            ]
        )

    raw = pd.concat(df_list, ignore_index=True)
    raw["Price[Currency/MWh]"] = pd.to_numeric(
        raw["Price[Currency/MWh]"], errors="coerce"
    )
    raw["timestamp"] = pd.to_datetime(raw["DateTime(UTC)"], utc=True).dt.tz_convert(
        "Europe/Vienna"
    )

    prices = (
        raw.pivot_table(
            index="timestamp",
            columns="AreaMapCode",
            values="Price[Currency/MWh]",
            aggfunc="mean",
        )
        .resample("1h")
        .mean()
    )

    prices.columns = [f"Price_{col}" for col in prices.columns]
    return prices


def load_and_filter_flows(folder_path: str) -> pd.DataFrame:
    files = sorted(glob.glob(f"{folder_path}/**/*.csv", recursive=True))
    if not files:
        raise FileNotFoundError(f"No flow files found in '{folder_path}'.")

    df_list = []
    for f in files:
        df = pd.read_csv(f, sep="\t", low_memory=False)
        cols_lower = {col.lower().strip(): col for col in df.columns}

        out_candidates = ["outareamapcode", "outmapcode", "outbzn", "fromarea"]
        out_col = next((cols_lower[c] for c in out_candidates if c in cols_lower), None)

        in_candidates = ["inareamapcode", "inmapcode", "inbzn", "toarea"]
        in_col = next((cols_lower[c] for c in in_candidates if c in cols_lower), None)

        time_candidates = ["datetime(utc)", "datetime", "time(utc)"]
        time_col = next((cols_lower[c] for c in time_candidates if c in cols_lower), None)

        flow_candidates = [
            "flowvalue", "physicalflow", "flowvalue[mw]", "flow[mw]",
            "value", "quantity", "crossborderflow"
        ]
        flow_col = next((cols_lower[c] for c in flow_candidates if c in cols_lower), None)

        if flow_col is None:
            flow_col = next((col for col in df.columns if "flow" in col.lower() or "value" in col.lower()), None)

        if not all([out_col, in_col, time_col, flow_col]):
            print(f"Columns in {f}: {list(df.columns)}")
            raise KeyError("Critical flow columns could not be mapped automatically.")

        mask = df[out_col].isin(ZONES) & df[in_col].isin(ZONES)
        df_filtered = df[mask].copy()

        df_filtered["Border"] = "Flow_" + df_filtered[out_col] + "_to_" + df_filtered[in_col]
        df_list.append(df_filtered[[time_col, "Border", flow_col]])

    raw = pd.concat(df_list, ignore_index=True)
    time_col_name = raw.columns[0]
    flow_col_name = raw.columns[2]

    raw[flow_col_name] = pd.to_numeric(raw[flow_col_name], errors="coerce")
    raw["timestamp"] = pd.to_datetime(raw[time_col_name], utc=True).dt.tz_convert("Europe/Vienna")

    flows = (
        raw.pivot_table(
            index="timestamp",
            columns="Border",
            values=flow_col_name,
            aggfunc="mean",
        )
        .resample("1h")
        .mean()
    )

    return flows


if __name__ == "__main__":
    print("1/3 Reading Day-Ahead prices...")
    df_prices = load_and_filter_prices("raw/prices")
    print(f"Prices successfully loaded ({df_prices.shape[0]} hours).")

    print("2/3 Reading physical flows...")
    df_flows = load_and_filter_flows("raw/flows")
    print(f"Border flows successfully loaded. Relations: {list(df_flows.columns)}")

    print("3/3 Calculating spreads and saving Parquet...")
    df_master = df_prices.join(df_flows, how="inner")

    if "Price_AT" in df_master and "Price_DE_LU" in df_master:
        df_master["Spread_AT_DE"] = df_master["Price_AT"] - df_master["Price_DE_LU"]
    if "Price_CH" in df_master and "Price_DE_LU" in df_master:
        df_master["Spread_CH_DE"] = df_master["Price_CH"] - df_master["Price_DE_LU"]
    if "Price_CH" in df_master and "Price_AT" in df_master:
        df_master["Spread_CH_AT"] = df_master["Price_CH"] - df_master["Price_AT"]

    out_dir = Path("processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "dach_market_data.parquet"

    df_master.to_parquet(out_file)
    print(f"\nDone! Dataset saved to: {out_file.resolve()}")
    print(f"Total shape: {df_master.shape[0]} hours, {df_master.shape[1]} columns.")