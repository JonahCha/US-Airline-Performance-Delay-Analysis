"""Static charts for the README. Writes PNGs to docs/images."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def save_figures(summary: dict, figdir: Path) -> list[Path]:
    figdir.mkdir(parents=True, exist_ok=True)
    paths = [
        _cancel_reasons(summary, figdir / "cancellation_reasons.png"),
        _ontime_by_airline(summary, figdir / "ontime_by_airline.png"),
        _monthly_cancellations(summary, figdir / "monthly_cancellations.png"),
    ]
    if "airports_geo" in summary:
        paths.append(_airport_map(summary, figdir / "airport_map.png"))
    return paths


def _finish(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _cancel_reasons(s: dict, path: Path) -> Path:
    reasons = s["cancel_reasons"]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.barh(reasons.index[::-1], reasons.values[::-1], color=PALETTE[1])
    ax.bar_label(bars, labels=[f"{v:,}" for v in reasons.values[::-1]])
    ax.set_title("Why flights were cancelled")
    ax.set_xlabel("Cancelled flights")
    return _finish(fig, path)


def _ontime_by_airline(s: dict, path: Path) -> Path:
    by = s["by_airline"]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(by.index[::-1], by["on_time_rate"].values[::-1] * 100, color=PALETTE[0])
    ax.bar_label(bars, labels=[f"{v:.1%}" for v in by["on_time_rate"].values[::-1]], fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_title("On-time arrival rate by airline (within 15 minutes)")
    ax.set_xlabel("On-time rate (%)")
    return _finish(fig, path)


def _monthly_cancellations(s: dict, path: Path) -> Path:
    m = s["monthly"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot([MONTHS[i - 1] for i in m.index], m["cancelled"].values, marker="o", color=PALETTE[2])
    ax.set_title("Cancelled flights by month")
    ax.set_ylabel("Cancelled flights")
    ax.grid(alpha=0.3)
    return _finish(fig, path)


def _airport_map(s: dict, path: Path) -> Path:
    geo = s["airports_geo"].dropna(subset=["LATITUDE", "LONGITUDE"])
    geo = geo[geo["flights"] > 0]
    fig, ax = plt.subplots(figsize=(10, 6))
    sc = ax.scatter(
        geo["LONGITUDE"], geo["LATITUDE"],
        s=geo["flights"] / geo["flights"].max() * 800 + 4,
        c=geo["on_time_rate"] * 100, cmap="RdYlGn", vmin=50, vmax=95,
        alpha=0.75, edgecolors="grey", linewidths=0.3,
    )
    fig.colorbar(sc, ax=ax, label="On-time rate (%)")
    ax.set_title("Where the flights start: bubble size = flights, colour = on-time rate")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.2)
    return _finish(fig, path)
