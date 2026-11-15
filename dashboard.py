"""Interactive HTML dashboard for the airline analysis.

Writes one self-contained file, dashboard.html. Open it in any browser:
hover for details, use the dropdown to switch the airline view, zoom and
pan the map, and click legend items to hide them.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TOP_AIRPORTS = 15


def build_dashboard(summary: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    fig = make_subplots(
        rows=4, cols=4,
        specs=[
            [{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}],
            [{"type": "xy", "colspan": 2}, None, {"type": "domain", "colspan": 2}, None],
            [{"type": "xy", "colspan": 2}, None, {"type": "xy", "colspan": 2}, None],
            [{"type": "xy", "colspan": 4}, None, None, None],
        ],
        row_heights=[0.12, 0.30, 0.26, 0.42],
        vertical_spacing=0.07,
        subplot_titles=(
            "", "", "", "",
            "Airlines: on-time arrivals", "Why flights were cancelled",
            "Cancelled flights by month", f"Top {TOP_AIRPORTS} busiest origin airports",
            "Where the flights start (bubble size = flights, colour = on-time rate)", None, None, None,
        ),
    )

    # KPI tiles
    kpis = [
        ("Flights analysed", summary["total_flights"], ","),
        ("On-time arrivals", summary["on_time_rate"] * 100, ".1f"),
        ("Cancelled", summary["cancellation_rate"] * 100, ".2f"),
        ("Mean arrival delay (min)", summary["mean_arrival_delay"], ".2f"),
    ]
    for col, (title, value, fmt) in enumerate(kpis, start=1):
        suffix = "%" if "%" in title or title in ("On-time arrivals", "Cancelled") else ""
        fig.add_trace(go.Indicator(
            mode="number", value=value, title={"text": title},
            number={"valueformat": fmt, "suffix": suffix, "font": {"size": 42}},
        ), row=1, col=col)

    # Airlines: switchable between on-time rate and flight count
    by = summary["by_airline"].sort_values("on_time_rate")
    airline_rate_trace = go.Bar(
        y=by.index, x=by["on_time_rate"] * 100, orientation="h",
        text=[f"{v:.1%}" for v in by["on_time_rate"]], textposition="outside",
        marker=dict(color=by["on_time_rate"], colorscale="RdYlGn", cmin=0.7, cmax=0.9),
        customdata=by["flights"],
        hovertemplate="<b>%{y}</b><br>On time: %{x:.1f}%<br>Flights: %{customdata:,}<extra></extra>",
        name="On-time rate",
    )
    fig.add_trace(airline_rate_trace, row=2, col=1)
    airline_idx = len(fig.data) - 1
    fig.update_xaxes(title_text="On-time rate (%)", row=2, col=1, range=[0, 100])

    # Cancellation causes donut
    reasons = summary["cancel_reasons"]
    fig.add_trace(go.Pie(
        labels=reasons.index, values=reasons.values, hole=0.55,
        textinfo="label+percent", sort=False,
        hovertemplate="<b>%{label}</b><br>%{value:,} flights<br>%{percent}<extra></extra>",
    ), row=2, col=3)

    # Monthly cancellations
    m = summary["monthly"]
    fig.add_trace(go.Scatter(
        x=[MONTHS[i - 1] for i in m.index], y=m["cancelled"], mode="lines+markers",
        line=dict(width=3, color="#FF6F61"), marker=dict(size=9),
        customdata=m["cancel_rate"] * 100,
        hovertemplate="<b>%{x}</b><br>Cancelled: %{y:,}<br>Rate: %{customdata:.2f}%<extra></extra>",
        name="Cancelled",
    ), row=3, col=1)
    fig.update_yaxes(title_text="Cancelled flights", row=3, col=1)

    # Busiest airports, coloured by on-time rate
    top = summary["airports_geo"].sort_values("flights", ascending=False).head(TOP_AIRPORTS)
    top = top.sort_values("flights")
    labels = [
        f"{code} {row['CITY']}" if isinstance(row.get("CITY"), str) else code
        for code, row in top.iterrows()
    ]
    fig.add_trace(go.Bar(
        y=labels, x=top["flights"], orientation="h",
        marker=dict(color=top["on_time_rate"] * 100, colorscale="RdYlGn", cmin=70, cmax=90,
                    ),
        text=[f"{v:.0%} on time" for v in top["on_time_rate"]], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Flights: %{x:,}<br>%{text}<extra></extra>",
        name="Airports",
    ), row=3, col=3)

    # Map of origin airports
    geo = summary["airports_geo"].dropna(subset=["LATITUDE", "LONGITUDE"])
    geo = geo[geo["flights"] > 0]
    fig.add_trace(go.Scatter(
        x=geo["LONGITUDE"], y=geo["LATITUDE"], mode="markers",
        marker=dict(
            size=(geo["flights"] / geo["flights"].max() * 38).clip(lower=4),
            color=geo["on_time_rate"] * 100, colorscale="RdYlGn", cmin=60, cmax=95,
            line=dict(width=0.5, color="#222"), opacity=0.85,
            colorbar=dict(title="On time %", x=1.02, y=0.2, len=0.4, thickness=14),
        ),
        customdata=list(zip(
            geo.index, geo["AIRPORT"].fillna(""), geo["CITY"].fillna(""),
            geo["flights"], geo["on_time_rate"] * 100, geo["cancel_rate"] * 100,
        )),
        hovertemplate=(
            "<b>%{customdata[0]}</b> %{customdata[2]}<br>%{customdata[1]}<br>"
            "Flights: %{customdata[3]:,}<br>On time: %{customdata[4]:.1f}%<br>"
            "Cancelled: %{customdata[5]:.2f}%<extra></extra>"
        ),
        name="Airports",
    ), row=4, col=1)
    fig.update_xaxes(title_text="Longitude", row=4, col=1, showgrid=False, range=[-170, -65])
    fig.update_yaxes(title_text="Latitude", row=4, col=1, showgrid=False, range=[15, 72])

    # Dropdown: switch the airline chart between on-time rate and flight count
    fig.update_layout(
        updatemenus=[dict(
            type="dropdown", x=0.0, y=0.90, xanchor="left", yanchor="top", bgcolor="#1f2a36",
            buttons=[
                dict(label="On-time rate", method="restyle",
                     args=[{"x": [by["on_time_rate"] * 100],
                            "text": [[f"{v:.1%}" for v in by["on_time_rate"]]],
                            "customdata": [by["flights"]],
                            "hovertemplate": ["<b>%{y}</b><br>On time: %{x:.1f}%<br>Flights: %{customdata:,}<extra></extra>"]},
                           [airline_idx]]),
                dict(label="Number of flights", method="restyle",
                     args=[{"x": [by["flights"]],
                            "text": [[f"{v:,}" for v in by["flights"]]],
                            "customdata": [by["on_time_rate"] * 100],
                            "hovertemplate": ["<b>%{y}</b><br>Flights: %{x:,}<br>On time: %{customdata:.1f}%<extra></extra>"]},
                           [airline_idx]]),
            ],
        )],
        template="plotly_dark",
        title=dict(text="✈️ US Airline Performance, 2015", x=0.5, font=dict(size=28)),
        height=1750,
        showlegend=False,
        margin=dict(t=120, b=40, l=40, r=80),
        paper_bgcolor="#0e1117",
    )
    fig.write_html(path, include_plotlyjs=True, full_html=True)
    return path
