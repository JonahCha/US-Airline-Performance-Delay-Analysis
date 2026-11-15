"""US airline performance analysis (BTS 2015 flight delay data).

Cleans and merges the flight, airline and airport tables, then computes
on-time performance, cancellation causes, airport and monthly trends.

The flights file is read in chunks and the counts are added up as it goes,
so the full 5.8-million-row file fits in a few gigabytes of memory.

Usage:
    python airline_analysis.py --flights data/flights.csv --outdir docs
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dashboard import build_dashboard
from plots import save_figures

DEFAULT_AIRLINES = Path("data/airlines.csv")
DEFAULT_AIRPORTS = Path("data/airports.csv")
DEFAULT_FLIGHTS = Path("data/flights.csv")
DEFAULT_OUTDIR = Path("docs")
CHUNK_ROWS = 500_000

DELAY_COLUMNS = [
    "AIR_SYSTEM_DELAY", "SECURITY_DELAY", "AIRLINE_DELAY",
    "LATE_AIRCRAFT_DELAY", "WEATHER_DELAY",
]
REQUIRED_FLIGHT_COLUMNS = {
    "YEAR", "MONTH", "DAY", "AIRLINE", "ORIGIN_AIRPORT",
    "DESTINATION_AIRPORT", "ARRIVAL_DELAY", "CANCELLED",
}
# BTS cancellation codes
CANCELLATION_REASONS = {"A": "Carrier", "B": "Weather", "C": "National Air System", "D": "Security"}
ON_TIME_THRESHOLD_MIN = 15  # FAA definition: arrived within 15 minutes of schedule

# Only these columns are read from the flights file.
FLIGHT_COLUMNS = REQUIRED_FLIGHT_COLUMNS | set(DELAY_COLUMNS) | {"CANCELLATION_REASON"}
FLIGHT_DTYPES = {
    "YEAR": "int16", "MONTH": "int8", "DAY": "int8", "CANCELLED": "int8",
    "AIRLINE": "category", "ORIGIN_AIRPORT": "category",
    "DESTINATION_AIRPORT": "category", "CANCELLATION_REASON": "category",
    "ARRIVAL_DELAY": "float32", **{c: "float32" for c in DELAY_COLUMNS},
}


def clean_flights(flights: pd.DataFrame, airlines: pd.DataFrame, airports: pd.DataFrame) -> pd.DataFrame:
    """Return flights with a FLIGHT_DATE, airline name, and origin and destination airport details."""
    missing = REQUIRED_FLIGHT_COLUMNS - set(flights.columns)
    if missing:
        raise ValueError(f"Flights file is missing columns: {sorted(missing)}")

    df = flights.copy()
    delay_cols = [c for c in DELAY_COLUMNS if c in df.columns]
    df[delay_cols] = df[delay_cols].fillna(0)  # blank delay reason means no delay of that type
    df["FLIGHT_DATE"] = pd.to_datetime(dict(year=df["YEAR"], month=df["MONTH"], day=df["DAY"]))

    # airlines.csv uses AIRLINE for the name; rename so it doesn't clash with the flight code
    names = airlines.rename(columns={"AIRLINE": "AIRLINE_NAME"})
    df = df.merge(names, left_on="AIRLINE", right_on="IATA_CODE", how="left").drop(columns="IATA_CODE")

    # Explicit prefixes keep origin and destination airport details separate
    origin = airports.rename(columns={c: f"ORIGIN_INFO_{c}" for c in airports.columns if c != "IATA_CODE"})
    df = df.merge(origin, left_on="ORIGIN_AIRPORT", right_on="IATA_CODE", how="left").drop(columns="IATA_CODE")

    dest = airports.rename(columns={c: f"DEST_INFO_{c}" for c in airports.columns if c != "IATA_CODE"})
    df = df.merge(dest, left_on="DESTINATION_AIRPORT", right_on="IATA_CODE", how="left").drop(columns="IATA_CODE")

    return df


def _partial(df: pd.DataFrame) -> dict:
    """Raw counts for one chunk of cleaned flights. These can be added across chunks."""
    cancelled = df["CANCELLED"].astype(bool)
    operated = df.loc[~cancelled].dropna(subset=["ARRIVAL_DELAY"])
    on_time = operated["ARRIVAL_DELAY"] <= ON_TIME_THRESHOLD_MIN

    by_airline = (
        pd.DataFrame({"AIRLINE_NAME": operated["AIRLINE_NAME"].astype(object), "ON_TIME": on_time.values})
        .groupby("AIRLINE_NAME")["ON_TIME"]
        .agg(flights="size", on_time="sum")
    )
    reasons = (
        df.loc[cancelled, "CANCELLATION_REASON"].astype(object)
        .map(CANCELLATION_REASONS).fillna("Unknown").value_counts()
    )
    monthly = (
        df.groupby(df["FLIGHT_DATE"].dt.month)
        .agg(flights=("CANCELLED", "size"), cancelled=("CANCELLED", "sum"))
    )
    all_by_origin = (
        pd.DataFrame({"ORIGIN": df["ORIGIN_AIRPORT"].astype(object).values, "CANCELLED": df["CANCELLED"].values})
        .groupby("ORIGIN")["CANCELLED"].agg(flights="size", cancelled="sum")
    )
    ontime_by_origin = (
        pd.DataFrame({"ORIGIN": operated["ORIGIN_AIRPORT"].astype(object).values, "ON_TIME": on_time.values})
        .groupby("ORIGIN")["ON_TIME"].agg(operated="size", on_time="sum")
    )
    airports = all_by_origin.join(ontime_by_origin, how="outer").fillna(0)

    return {
        "total": len(df),
        "cancelled": int(cancelled.sum()),
        "operated": len(operated),
        "on_time": int(on_time.sum()),
        "delay_sum": float(operated["ARRIVAL_DELAY"].sum()),
        "reasons": reasons,
        "by_airline": by_airline,
        "monthly": monthly,
        "airports": airports,
    }


def combine(partials: list[dict]) -> dict:
    """Add up chunk counts and turn them into the summary used by reports, charts and the dashboard."""
    total = sum(p["total"] for p in partials)
    cancelled = sum(p["cancelled"] for p in partials)
    operated = sum(p["operated"] for p in partials)
    on_time = sum(p["on_time"] for p in partials)
    delay_sum = sum(p["delay_sum"] for p in partials)

    reasons = pd.concat([p["reasons"] for p in partials]).groupby(level=0).sum().sort_values(ascending=False)
    by_airline = pd.concat([p["by_airline"] for p in partials]).groupby(level=0).sum()
    by_airline["on_time_rate"] = by_airline["on_time"] / by_airline["flights"]
    by_airline = by_airline[["flights", "on_time_rate"]].sort_values("on_time_rate", ascending=False)
    monthly = pd.concat([p["monthly"] for p in partials]).groupby(level=0).sum().sort_index()
    monthly["cancel_rate"] = monthly["cancelled"] / monthly["flights"]

    airports = pd.concat([p["airports"] for p in partials]).groupby(level=0).sum()
    airports["on_time_rate"] = (airports["on_time"] / airports["operated"]).fillna(0)
    airports["cancel_rate"] = (airports["cancelled"] / airports["flights"]).fillna(0)

    return {
        "total_flights": total,
        "cancelled": cancelled,
        "cancellation_rate": cancelled / total if total else 0.0,
        "operated": operated,
        "on_time_rate": on_time / operated if operated else 0.0,
        "mean_arrival_delay": delay_sum / operated if operated else 0.0,
        "cancel_reasons": reasons,
        "by_airline": by_airline,
        "monthly": monthly,
        "airports": airports,
    }


def summarize(df: pd.DataFrame) -> dict:
    """Summary for a flights table that fits in memory."""
    return combine([_partial(df)])


def iter_clean_chunks(flights_path: Path, airlines: pd.DataFrame, airports: pd.DataFrame, chunk_rows: int = CHUNK_ROWS):
    reader = pd.read_csv(
        flights_path,
        usecols=lambda c: c in FLIGHT_COLUMNS,
        dtype=FLIGHT_DTYPES,
        chunksize=chunk_rows,
    )
    for chunk in reader:
        yield clean_flights(chunk, airlines, airports)


def format_report(s: dict) -> str:
    lines = [
        f"Total flights: {s['total_flights']:,}",
        f"Cancelled: {s['cancelled']:,} ({s['cancellation_rate']:.2%})",
        f"On-time arrivals (within {ON_TIME_THRESHOLD_MIN} min, operated flights): {s['on_time_rate']:.1%}",
        f"Mean arrival delay (operated flights): {s['mean_arrival_delay']:.2f} minutes",
        "",
        "Cancellation causes (share of cancelled flights):",
    ]
    total_cancelled = max(s["cancelled"], 1)
    for reason, count in s["cancel_reasons"].items():
        lines.append(f"  {reason:22s} {count:,} ({count / total_cancelled:.1%})")
    lines += ["", "On-time rate by airline (highest first):"]
    for name, row in s["by_airline"].iterrows():
        lines.append(f"  {name:32s} {row['on_time_rate']:.1%}  ({int(row['flights']):,} flights)")
    if "airports_geo" in s:
        busiest = s["airports_geo"].sort_values("flights", ascending=False).head(10)
        lines += ["", "Busiest origin airports:"]
        for code, row in busiest.iterrows():
            name = row.get("AIRPORT") if isinstance(row.get("AIRPORT"), str) else code
            lines.append(f"  {code}  {name:42s} {int(row['flights']):,} flights, {row['on_time_rate']:.1%} on time")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--flights", type=Path, default=DEFAULT_FLIGHTS)
    parser.add_argument("--airlines", type=Path, default=DEFAULT_AIRLINES)
    parser.add_argument("--airports", type=Path, default=DEFAULT_AIRPORTS)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    if not args.flights.exists():
        raise SystemExit(f"Flights file not found: {args.flights}. See data/README.md for how to get it.")

    airlines_df = pd.read_csv(args.airlines)
    airports_df = pd.read_csv(args.airports)
    partials = [_partial(df) for df in iter_clean_chunks(args.flights, airlines_df, airports_df)]
    summary = combine(partials)

    geo = airports_df.set_index("IATA_CODE")[["AIRPORT", "CITY", "STATE", "LATITUDE", "LONGITUDE"]]
    summary["airports_geo"] = summary["airports"].join(geo, how="left")

    report = format_report(summary)
    print(report)

    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / "results.txt").write_text(report + "\n", encoding="utf-8")
    save_figures(summary, args.outdir / "images")
    build_dashboard(summary, args.outdir / "dashboard.html")


if __name__ == "__main__":
    main()
