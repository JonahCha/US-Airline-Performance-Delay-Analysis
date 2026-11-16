import numpy as np
import pandas as pd
import pytest

from airline_analysis import clean_flights, format_report, summarize
from plots import save_figures


def make_inputs(n=300, seed=0):
    rng = np.random.default_rng(seed)
    cancelled = (rng.uniform(size=n) < 0.05).astype(int)
    arrival = rng.normal(5, 25, n).round()
    arrival = np.where(cancelled == 1, np.nan, arrival)
    flights = pd.DataFrame({
        "YEAR": 2015,
        "MONTH": rng.integers(1, 13, n),
        "DAY": rng.integers(1, 29, n),
        "AIRLINE": rng.choice(["AA", "DL"], n),
        "ORIGIN_AIRPORT": rng.choice(["JFK", "LAX"], n),
        "DESTINATION_AIRPORT": rng.choice(["LAX", "JFK"], n),
        "ARRIVAL_DELAY": arrival,
        "CANCELLED": cancelled,
        "CANCELLATION_REASON": np.where(cancelled == 1, rng.choice(["A", "B", "C"], n).astype(object), None),
        "AIRLINE_DELAY": np.where(rng.uniform(size=n) < 0.3, np.nan, 3.0),
        "WEATHER_DELAY": np.nan,
    })
    airlines = pd.DataFrame({"IATA_CODE": ["AA", "DL"], "AIRLINE": ["American Airlines Inc.", "Delta Air Lines Inc."]})
    airports = pd.DataFrame({
        "IATA_CODE": ["JFK", "LAX"],
        "AIRPORT": ["John F. Kennedy", "Los Angeles Intl"],
        "CITY": ["New York", "Los Angeles"],
        "STATE": ["NY", "CA"], "COUNTRY": ["USA", "USA"],
        "LATITUDE": [40.6, 33.9], "LONGITUDE": [-73.8, -118.4],
    })
    return flights, airlines, airports


def test_clean_adds_date_names_and_airport_details():
    flights, airlines, airports = make_inputs()
    df = clean_flights(flights, airlines, airports)
    assert len(df) == len(flights)
    assert pd.api.types.is_datetime64_any_dtype(df["FLIGHT_DATE"])
    assert set(df["AIRLINE_NAME"].dropna()) <= {"American Airlines Inc.", "Delta Air Lines Inc."}
    assert "ORIGIN_INFO_CITY" in df.columns and "DEST_INFO_CITY" in df.columns
    assert "IATA_CODE" not in df.columns


def test_clean_fills_missing_delay_reasons_with_zero():
    flights, airlines, airports = make_inputs()
    df = clean_flights(flights, airlines, airports)
    assert df["AIRLINE_DELAY"].notna().all()


def test_clean_rejects_missing_columns():
    flights, airlines, airports = make_inputs()
    with pytest.raises(ValueError, match="missing columns"):
        clean_flights(flights.drop(columns="CANCELLED"), airlines, airports)


def test_summary_on_time_and_cancellation_rates():
    df = pd.DataFrame({
        "FLIGHT_DATE": pd.to_datetime(["2015-01-01"] * 4),
        "AIRLINE_NAME": ["A", "A", "B", "B"],
        "CANCELLED": [0, 0, 0, 1],
        "ARRIVAL_DELAY": [10.0, 30.0, 15.0, np.nan],
        "CANCELLATION_REASON": [np.nan, np.nan, np.nan, "C"],
        "ORIGIN_AIRPORT": ["JFK", "JFK", "LAX", "LAX"],
    })
    s = summarize(df)
    assert s["total_flights"] == 4
    assert s["cancelled"] == 1
    assert s["cancellation_rate"] == pytest.approx(0.25)
    # operated flights: delays 10, 30, 15 -> on time (<=15): 10 and 15
    assert s["on_time_rate"] == pytest.approx(2 / 3)
    assert s["cancel_reasons"].to_dict() == {"National Air System": 1}


def test_report_and_figures_are_written(tmp_path):
    flights, airlines, airports = make_inputs()
    s = summarize(clean_flights(flights, airlines, airports))
    text = format_report(s)
    assert "On-time arrivals" in text and "Cancellation causes" in text
    paths = save_figures(s, tmp_path / "images")
    assert len(paths) == 3
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


def test_chunked_summary_matches_single_pass():
    from airline_analysis import _partial, combine
    flights, airlines, airports = make_inputs(n=600)
    df = clean_flights(flights, airlines, airports)
    whole = summarize(df)
    chunks = [df.iloc[:200], df.iloc[200:450], df.iloc[450:]]
    parts = combine([_partial(c) for c in chunks])
    assert parts["total_flights"] == whole["total_flights"]
    assert parts["cancelled"] == whole["cancelled"]
    assert parts["on_time_rate"] == pytest.approx(whole["on_time_rate"])
    assert parts["mean_arrival_delay"] == pytest.approx(whole["mean_arrival_delay"])
    assert parts["cancel_reasons"].to_dict() == whole["cancel_reasons"].to_dict()
    assert parts["by_airline"]["flights"].to_dict() == whole["by_airline"]["flights"].to_dict()


def test_airport_and_monthly_aggregates_are_present():
    flights, airlines, airports = make_inputs(n=300)
    s = summarize(clean_flights(flights, airlines, airports))
    assert set(s["airports"].index) <= {"JFK", "LAX"}
    assert s["airports"]["flights"].sum() == s["total_flights"]
    assert s["monthly"]["flights"].sum() == s["total_flights"]
    assert s["monthly"]["cancelled"].sum() == s["cancelled"]


def test_dashboard_html_is_written(tmp_path):
    from dashboard import build_dashboard
    flights, airlines, airports = make_inputs(n=300)
    airports = airports.copy()
    s = summarize(clean_flights(flights, airlines, airports))
    geo = airports.set_index("IATA_CODE")[["AIRPORT", "CITY", "STATE", "LATITUDE", "LONGITUDE"]]
    s["airports_geo"] = s["airports"].join(geo, how="left")
    out = build_dashboard(s, tmp_path / "dashboard.html")
    html = out.read_text(encoding="utf-8")
    assert out.exists() and out.stat().st_size > 1_000_000  # Plotly JS is embedded
    assert "On-time rate" in html and "Number of flights" in html


def test_explorer_html_contains_all_tables(tmp_path):
    from explorer import build_explorer
    flights, airlines, airports = make_inputs(n=300)
    s = summarize(clean_flights(flights, airlines, airports))
    geo = airports.set_index("IATA_CODE")[["AIRPORT", "CITY", "STATE", "LATITUDE", "LONGITUDE"]]
    s["airports_geo"] = s["airports"].join(geo, how="left")
    out = build_explorer(s, tmp_path / "explorer.html")
    html = out.read_text(encoding="utf-8")
    assert '"airlines":' in html and '"airports":' in html and '"causes":' in html
    assert "American Airlines Inc." in html
    assert "</script>" in html and html.count("</script>") == 1
