"""Searchable, sortable data explorer: one self-contained HTML page.

Every table behind the dashboard is here. Search, sort any column, and click a
row to see its full breakdown. The page works offline, with no server needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def _records(df: pd.DataFrame) -> list[dict]:
    """Rows as dicts, with NaN turned into null."""
    return json.loads(df.to_json(orient="records"))


def _payload(summary: dict) -> dict:
    airlines = summary["by_airline"].reset_index()
    airlines = airlines.rename(columns={"AIRLINE_NAME": "name"})
    airlines = airlines[["name", "all_flights", "operated", "cancelled",
                         "on_time_rate", "cancel_rate", "mean_delay"]]

    geo = summary["airports_geo"].reset_index().rename(columns={"index": "code", "ORIGIN": "code"})
    geo = geo.rename(columns={"AIRPORT": "name", "CITY": "city", "STATE": "state",
                              "LATITUDE": "lat", "LONGITUDE": "lon"})
    geo["name"] = geo["name"].fillna(geo["code"])
    airports = geo[["code", "name", "city", "state", "flights", "cancelled",
                    "on_time_rate", "cancel_rate", "lat", "lon"]]

    monthly = summary["monthly"].reset_index()
    monthly["month"] = monthly.iloc[:, 0].map(lambda m: MONTHS[int(m) - 1])
    monthly = monthly[["month", "flights", "cancelled", "cancel_rate"]]

    reasons = summary["cancel_reasons"]
    causes = pd.DataFrame({
        "cause": reasons.index,
        "count": reasons.values,
        "share": reasons.values / max(summary["cancelled"], 1),
    })

    totals = {
        "flights": int(summary["total_flights"]),
        "cancelled": int(summary["cancelled"]),
        "cancellation_rate": float(summary["cancellation_rate"]),
        "on_time_rate": float(summary["on_time_rate"]),
        "mean_arrival_delay": float(summary["mean_arrival_delay"]),
    }
    return {
        "totals": totals,
        "airlines": _records(airlines),
        "airports": _records(airports),
        "months": _records(monthly),
        "causes": _records(causes),
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Airline Data Explorer</title>
<style>
  :root { --bg:#0e1117; --card:#161b22; --line:#2a313c; --text:#e6edf3; --muted:#8b949e;
          --accent:#58a6ff; --good:#3fb950; --bad:#f85149; --warn:#d29922; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background:var(--bg); color:var(--text); }
  header { padding:24px 32px 16px; border-bottom:1px solid var(--line); }
  h1 { margin:0; font-size:26px; }
  header p { margin:6px 0 14px; color:var(--muted); }
  .chips { display:flex; flex-wrap:wrap; gap:10px; }
  .chip { background:var(--card); border:1px solid var(--line); border-radius:999px; padding:6px 14px; font-size:14px; }
  .chip b { color:var(--accent); }
  .back { color:var(--accent); text-decoration:none; font-size:14px; }
  main { display:grid; grid-template-columns: minmax(0,2fr) minmax(280px,1fr); gap:20px; padding:20px 32px; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .tabs { display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap; }
  .tabs button { background:transparent; color:var(--muted); border:1px solid var(--line); border-radius:8px; padding:8px 14px; cursor:pointer; font-size:14px; }
  .tabs button.active { color:var(--text); border-color:var(--accent); background:#1c2a3a; }
  input#search { width:100%; padding:10px 12px; border-radius:8px; border:1px solid var(--line); background:#0d1117; color:var(--text); font-size:14px; margin-bottom:12px; }
  .scroll { max-height:68vh; overflow:auto; border-radius:8px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { padding:9px 10px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }
  th:first-child, td:first-child, th.text, td.text { text-align:left; }
  th { position:sticky; top:0; background:var(--card); color:var(--muted); cursor:pointer; user-select:none; font-weight:600; }
  th:hover { color:var(--text); }
  tbody tr { cursor:pointer; }
  tbody tr:hover { background:#1c2330; }
  tbody tr.selected { background:#1c2a3a; }
  .count { color:var(--muted); font-size:13px; margin:0 0 8px; }
  #detail h2 { margin:0 0 4px; font-size:20px; }
  #detail .sub { color:var(--muted); font-size:14px; margin-bottom:14px; }
  .stat { display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--line); font-size:14px; }
  .stat span:last-child { font-weight:600; }
  .bar { height:10px; border-radius:6px; background:#2a313c; overflow:hidden; margin:10px 0 4px; }
  .bar > div { height:100%; border-radius:6px; }
  .bar-label { color:var(--muted); font-size:12px; }
  .hint { color:var(--muted); font-size:14px; line-height:1.5; }
</style>
</head>
<body>
<header>
  <a class="back" href="index.html">← Back to project home</a>
  <h1>✈️ Airline Data Explorer</h1>
  <p>Every number behind the dashboard. Search, sort any column, and click a row for its full breakdown.</p>
  <div class="chips" id="chips"></div>
</header>
<main>
  <section class="card">
    <div class="tabs" id="tabs"></div>
    <input id="search" type="search" placeholder="Search airline name, airport code, or city…">
    <p class="count" id="count"></p>
    <div class="scroll"><table><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
  </section>
  <aside class="card" id="detail">
    <h2>Details</h2>
    <p class="hint">Click any row in the table to see its full breakdown here.<br><br>
    Tip: click a column header to sort. Click it again to reverse the order.</p>
  </aside>
</main>

<script>
const DATA = __DATA__;

const VIEWS = {
  airlines: {
    label: "Airlines", key: "name", rows: DATA.airlines,
    cols: [
      ["name", "Airline", "text", "Carrier name"],
      ["all_flights", "Flights", "int", "All scheduled flights in the file"],
      ["on_time_rate", "On time", "pct", "Share of operated flights arriving within 15 minutes of schedule"],
      ["cancel_rate", "Cancelled", "pct", "Share of all flights that were cancelled"],
      ["mean_delay", "Avg delay (min)", "num", "Average arrival delay of operated flights, in minutes"],
    ],
  },
  airports: {
    label: "Airports", key: "code", rows: DATA.airports,
    cols: [
      ["code", "Code", "text", "IATA airport code"],
      ["name", "Airport", "text", "Airport name"],
      ["city", "City", "text", ""],
      ["flights", "Departures", "int", "Flights departing from this airport"],
      ["on_time_rate", "On time", "pct", "Share of operated departures arriving within 15 minutes"],
      ["cancel_rate", "Cancelled", "pct", "Share of departures cancelled"],
    ],
  },
  months: {
    label: "Months", key: "month", rows: DATA.months,
    cols: [
      ["month", "Month", "text", ""],
      ["flights", "Flights", "int", "All flights scheduled in the month"],
      ["cancelled", "Cancelled", "int", "Flights cancelled in the month"],
      ["cancel_rate", "Cancel rate", "pct", "Cancelled flights as a share of all flights that month"],
    ],
  },
  causes: {
    label: "Cancellation causes", key: "cause", rows: DATA.causes,
    cols: [
      ["cause", "Cause", "text", "BTS cancellation code: Carrier, Weather, National Air System, or Security"],
      ["count", "Cancelled flights", "int", ""],
      ["share", "Share", "pct", "Share of all cancelled flights"],
    ],
  },
};

let current = "airlines", sortKey = null, sortDir = 1, visibleRows = [], selectedIdx = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (v, t) => {
  if (v === null || v === undefined) return "–";
  if (t === "pct") return (Number(v) * 100).toFixed(1) + "%";
  if (t === "int") return Math.round(Number(v)).toLocaleString("en-US");
  if (t === "num") return Number(v).toFixed(2);
  return esc(v);
};
const pctColour = (r) => r >= 0.85 ? "var(--good)" : r >= 0.78 ? "var(--warn)" : "var(--bad)";

function renderChips() {
  const t = DATA.totals;
  document.getElementById("chips").innerHTML = [
    `Flights <b>${fmt(t.flights, "int")}</b>`,
    `On time <b>${fmt(t.on_time_rate, "pct")}</b>`,
    `Cancelled <b>${fmt(t.cancellation_rate, "pct")}</b>`,
    `Avg delay <b>${t.mean_arrival_delay.toFixed(2)} min</b>`,
  ].map((c) => `<span class="chip">${c}</span>`).join("");
}

function renderTabs() {
  document.getElementById("tabs").innerHTML = Object.keys(VIEWS).map((k) =>
    `<button data-view="${k}" class="${k === current ? "active" : ""}">${VIEWS[k].label}</button>`
  ).join("");
}

function render() {
  const view = VIEWS[current];
  const q = document.getElementById("search").value.trim().toLowerCase();
  const textCols = view.cols.filter((c) => c[2] === "text").map((c) => c[0]);

  let rows = view.rows.filter((r) => !q || textCols.some((k) => String(r[k] ?? "").toLowerCase().includes(q)));
  if (sortKey) {
    rows = [...rows].sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * sortDir;
    });
  }
  visibleRows = rows;

  document.getElementById("thead").innerHTML = "<tr>" + view.cols.map((c) =>
    `<th data-k="${c[0]}" class="${c[2] === "text" ? "text" : ""}" title="${esc(c[3])}">${esc(c[1])}` +
    `${sortKey === c[0] ? (sortDir > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr>";

  document.getElementById("tbody").innerHTML = rows.map((r, i) =>
    `<tr data-i="${i}" class="${i === selectedIdx ? "selected" : ""}">` +
    view.cols.map((c) => `<td class="${c[2] === "text" ? "text" : ""}">${fmt(r[c[0]], c[2])}</td>`).join("") +
    "</tr>").join("");

  document.getElementById("count").textContent = `${rows.length} of ${view.rows.length} ${view.label.toLowerCase()} shown`;
}

function stat(label, value) {
  return `<div class="stat"><span>${esc(label)}</span><span>${value}</span></div>`;
}

function bar(rate) {
  return `<div class="bar"><div style="width:${(rate * 100).toFixed(1)}%;background:${pctColour(rate)}"></div></div>` +
         `<div class="bar-label">On time: ${(rate * 100).toFixed(1)}%</div>`;
}

function showDetail(r) {
  const el = document.getElementById("detail");
  if (current === "airlines") {
    el.innerHTML = `<h2>${esc(r.name)}</h2><div class="sub">Airline</div>` +
      stat("All flights", fmt(r.all_flights, "int")) +
      stat("Operated flights", fmt(r.operated, "int")) +
      stat("Cancelled flights", fmt(r.cancelled, "int")) +
      stat("Cancellation rate", fmt(r.cancel_rate, "pct")) +
      stat("On-time rate", fmt(r.on_time_rate, "pct")) +
      stat("Average arrival delay", fmt(r.mean_delay, "num") + " min") + bar(r.on_time_rate);
  } else if (current === "airports") {
    const loc = r.lat != null ? `${Number(r.lat).toFixed(2)}, ${Number(r.lon).toFixed(2)}` : "–";
    const sub = r.lat != null
      ? `${esc(r.name)}${r.city ? " · " + esc(r.city) : ""}${r.state ? ", " + esc(r.state) : ""}`
      : "Not in the airport lookup table (code only)";
    el.innerHTML = `<h2>${esc(r.code)}</h2><div class="sub">${sub}</div>` +
      stat("Departures", fmt(r.flights, "int")) +
      stat("Cancelled", fmt(r.cancelled, "int")) +
      stat("Cancellation rate", fmt(r.cancel_rate, "pct")) +
      stat("On-time rate", fmt(r.on_time_rate, "pct")) +
      stat("Coordinates", loc) + bar(r.on_time_rate);
  } else if (current === "months") {
    el.innerHTML = `<h2>${esc(r.month)}</h2><div class="sub">Month</div>` +
      stat("Flights", fmt(r.flights, "int")) +
      stat("Cancelled", fmt(r.cancelled, "int")) +
      stat("Cancel rate", fmt(r.cancel_rate, "pct"));
  } else {
    el.innerHTML = `<h2>${esc(r.cause)}</h2><div class="sub">Cancellation cause</div>` +
      stat("Cancelled flights", fmt(r.count, "int")) +
      stat("Share of cancellations", fmt(r.share, "pct"));
  }
}

function setView(key) {
  current = key; sortKey = null; sortDir = 1; selectedIdx = null;
  document.getElementById("search").value = "";
  renderTabs(); render();
  document.getElementById("detail").innerHTML =
    '<h2>Details</h2><p class="hint">Click any row in the table to see its full breakdown here.</p>';
}

document.getElementById("tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (b) setView(b.dataset.view);
});
document.getElementById("search").addEventListener("input", () => { selectedIdx = null; render(); });
document.getElementById("thead").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-k]");
  if (!th) return;
  const k = th.dataset.k;
  if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; }
  render();
});
document.getElementById("tbody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-i]");
  if (!tr) return;
  selectedIdx = Number(tr.dataset.i);
  render();
  showDetail(visibleRows[selectedIdx]);
});

renderChips(); renderTabs(); render();
</script>
</body>
</html>
"""


def build_explorer(summary: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(_payload(summary)).replace("</", "<\\/")
    path.write_text(HTML_TEMPLATE.replace("__DATA__", data), encoding="utf-8")
    return path
