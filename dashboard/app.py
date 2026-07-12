"""
Streamlit dashboard for NHS A&E four-hour target performance.

Run:
    streamlit run dashboard/app.py

If data/nhs_ae.duckdb doesn't exist yet but the committed tidy CSV
(data/processed/ae_attendances_tidy.csv) does, it's built automatically on
first run - so a fresh clone or cloud deploy works without anyone having to
run src/clean.py / src/load_db.py by hand first. Re-run those manually to
refresh the dashboard with new raw monthly files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "nhs_ae.duckdb"
TIDY_CSV_PATH = REPO_ROOT / "data" / "processed" / "ae_attendances_tidy.csv"

sys.path.insert(0, str(REPO_ROOT / "src"))

TARGET_PCT = 95.0

# Ink and chrome tokens (see dataviz skill / references/palette.md)
INK_MUTED = "#898781"
GRID = "#e1e0d9"

# Single-series emphasis color and the de-emphasis gray used for context lines
ACCENT = "#2a78d6"
CONTEXT_GRAY = "#c3c2b7"

STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"

# Fixed categorical hue per region (validated for CVD separation) - color
# always follows the region, never its rank in a given chart.
REGION_COLORS = {
    "NHS ENGLAND EAST OF ENGLAND": "#2a78d6",
    "NHS ENGLAND LONDON": "#1baf7a",
    "NHS ENGLAND MIDLANDS": "#eda100",
    "NHS ENGLAND NORTH EAST AND YORKSHIRE": "#008300",
    "NHS ENGLAND NORTH WEST": "#4a3aa7",
    "NHS ENGLAND SOUTH EAST": "#e34948",
    "NHS ENGLAND SOUTH WEST": "#e87ba4",
}


def region_label(region: str) -> str:
    return region.replace("NHS ENGLAND ", "").title()


def status_color(pct: float) -> str:
    if pct >= TARGET_PCT:
        return STATUS_GOOD
    if pct >= 75:
        return STATUS_WARNING
    return STATUS_CRITICAL


def base_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK_MUTED, size=12),
        hoverlabel=dict(bgcolor="white", font_size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=GRID)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False)
    return fig


@st.cache_data
def load_data() -> pd.DataFrame:
    # Open a short-lived connection rather than sharing one across reruns via
    # st.cache_resource - DuckDB connection objects aren't guaranteed safe to
    # reuse across Streamlit's rerun/session machinery, and this function only
    # ever needs to run its query once (cached) so there's nothing to gain by
    # keeping a connection open.
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        df = con.execute(
            """
            SELECT period, org_code, org_name, region, total_attendances, in_4_hours, pct_in_4_hours
            FROM ae_attendances
            WHERE total_attendances > 0
            """
        ).fetchdf()
    df["period"] = pd.to_datetime(df["period"])
    return df


st.set_page_config(page_title="NHS A&E Four-Hour Target", layout="wide")

if not DB_PATH.exists():
    if TIDY_CSV_PATH.exists():
        from load_db import load as load_duckdb

        load_duckdb(TIDY_CSV_PATH, DB_PATH)
    else:
        st.error(
            f"Couldn't find {DB_PATH.relative_to(REPO_ROOT)} or "
            f"{TIDY_CSV_PATH.relative_to(REPO_ROOT)}. "
            "Run `python src/clean.py` then `python src/load_db.py` first."
        )
        st.stop()

df = load_data()

st.title("NHS A&E Performance: Who's Missing the Four-Hour Target")
st.caption(
    f"{df['period'].min():%B %Y} - {df['period'].max():%B %Y} · "
    f"{df['org_code'].nunique()} orgs · England's four-hour A&E standard is 95%"
)

# --- Sidebar filters ---
st.sidebar.header("Filters")
all_regions = sorted(df["region"].unique())
selected_regions = st.sidebar.multiselect(
    "Region", options=all_regions, default=all_regions, format_func=region_label,
    key="region_filter",
)

periods = sorted(df["period"].unique())
period_labels = [pd.Timestamp(p).strftime("%b %Y") for p in periods]
start_idx, end_idx = st.sidebar.select_slider(
    "Date range",
    options=list(range(len(periods))),
    value=(0, len(periods) - 1),
    format_func=lambda i: period_labels[i],
    key="date_range_filter",
)
start_period, end_period = periods[start_idx], periods[end_idx]

filtered = df[
    df["region"].isin(selected_regions)
    & df["period"].between(start_period, end_period)
]

if filtered.empty:
    st.warning("No data for the current filter selection.")
    st.stop()

latest_period = filtered["period"].max()
prior_period_candidates = sorted(p for p in filtered["period"].unique() if p < latest_period)
prior_period = prior_period_candidates[-1] if prior_period_candidates else None

# --- KPI row ---
national = filtered.groupby("period").agg(
    total=("total_attendances", "sum"), in4=("in_4_hours", "sum")
)
national["pct"] = 100 * national["in4"] / national["total"]

latest_pct = national.loc[latest_period, "pct"]
prior_pct = national.loc[prior_period, "pct"] if prior_period is not None else None
delta = latest_pct - prior_pct if prior_pct is not None else None

region_latest = (
    filtered[filtered["period"] == latest_period]
    .groupby("region")
    .agg(total=("total_attendances", "sum"), in4=("in_4_hours", "sum"))
)
region_latest["pct"] = 100 * region_latest["in4"] / region_latest["total"]
best_region = region_latest["pct"].idxmax()
worst_region = region_latest["pct"].idxmin()

trusts_meeting_target = (
    filtered[filtered["period"] == latest_period]
    .assign(pct=lambda d: 100 * d["in_4_hours"] / d["total_attendances"])
    .query("pct >= @TARGET_PCT")
    .shape[0]
)
trusts_total = filtered[filtered["period"] == latest_period]["org_code"].nunique()

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    f"National % in 4hrs ({latest_period:%b %Y})",
    f"{latest_pct:.1f}%",
    f"{delta:+.1f}pp vs prior month" if delta is not None else None,
)
col2.metric("Gap to 95% standard", f"{TARGET_PCT - latest_pct:.1f}pp")
col3.metric(f"Best region ({latest_period:%b %Y})", region_label(best_region), f"{region_latest.loc[best_region, 'pct']:.1f}%")
col4.metric(f"Trusts meeting target", f"{trusts_meeting_target} / {trusts_total}")

st.divider()

# --- National trend ---
st.subheader("National trend")
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=national.index, y=national["pct"], mode="lines+markers",
        line=dict(color=ACCENT, width=2), marker=dict(size=6, color=ACCENT),
        name="% in 4 hours",
        hovertemplate="%{x|%b %Y}<br>%{y:.1f}% in 4 hours<extra></extra>",
    )
)
fig.add_hline(
    y=TARGET_PCT, line_dash="dash", line_color=INK_MUTED, line_width=1,
    annotation_text="95% standard", annotation_position="top left",
    annotation_font_color=INK_MUTED,
)
fig.update_yaxes(title="% seen within 4 hours", range=[0, 100])
base_layout(fig)
st.plotly_chart(fig, width="stretch")

# --- Seasonality ---
st.subheader("Performance by calendar month")
seasonal = filtered.groupby(filtered["period"].dt.month).agg(
    total=("total_attendances", "sum"), in4=("in_4_hours", "sum")
)
seasonal["pct"] = 100 * seasonal["in4"] / seasonal["total"]
month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
seasonal = seasonal.reindex(range(1, 13))
seasonal_min, seasonal_max = seasonal["pct"].min(), seasonal["pct"].max()

def seq_shade(pct: float) -> str:
    if pd.isna(pct):
        return GRID
    t = (pct - seasonal_min) / max(seasonal_max - seasonal_min, 1e-9)
    # blue sequential ramp, light (near-zero) -> dark (high), per palette.md
    ramp = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95"]
    idx = min(int(t * (len(ramp) - 1)), len(ramp) - 1)
    return ramp[idx]

fig2 = go.Figure(
    go.Bar(
        x=month_names,
        y=seasonal["pct"],
        marker_color=[seq_shade(p) for p in seasonal["pct"]],
        hovertemplate="%{x}: %{y:.1f}% in 4 hours<extra></extra>",
    )
)
fig2.update_yaxes(title="% in 4 hours (volume-weighted)", range=[0, 100])
base_layout(fig2, height=320)
st.plotly_chart(fig2, width="stretch")

st.divider()

# --- Regional comparison ---
st.subheader(f"Regional comparison ({latest_period:%B %Y})")
st.caption(
    "Shown as a ranked comparison rather than a geographic map - the boundary "
    "files needed for a real choropleth weren't reachable from this environment."
)
region_latest_sorted = region_latest.sort_values("pct")
fig3 = go.Figure(
    go.Bar(
        x=region_latest_sorted["pct"],
        y=[region_label(r) for r in region_latest_sorted.index],
        orientation="h",
        marker_color=[REGION_COLORS[r] for r in region_latest_sorted.index],
        text=[f"{p:.1f}%" for p in region_latest_sorted["pct"]],
        textposition="outside",
        hovertemplate="%{y}: %{x:.1f}% in 4 hours<extra></extra>",
    )
)
fig3.add_vline(x=TARGET_PCT, line_dash="dash", line_color=INK_MUTED, line_width=1)
fig3.update_xaxes(title="% in 4 hours", range=[0, 105])
base_layout(fig3, height=320)
st.plotly_chart(fig3, width="stretch")

# --- Regional trend, small multiples ---
st.subheader("Regional trend over time")
region_trend = filtered.groupby(["region", "period"]).agg(
    total=("total_attendances", "sum"), in4=("in_4_hours", "sum")
)
region_trend["pct"] = 100 * region_trend["in4"] / region_trend["total"]

regions_in_order = [r for r in REGION_COLORS if r in selected_regions]
n = len(regions_in_order)
cols = 4
rows = (n + cols - 1) // cols
fig4 = make_subplots(
    rows=rows, cols=cols,
    subplot_titles=[region_label(r) for r in regions_in_order],
    shared_yaxes=True,
)
for i, region in enumerate(regions_in_order):
    r, c = divmod(i, cols)
    sub = region_trend.loc[region]
    fig4.add_trace(
        go.Scatter(
            x=national.index, y=national["pct"], mode="lines",
            line=dict(color=CONTEXT_GRAY, width=1.5, dash="dot"),
            name="England avg", showlegend=(i == 0), hoverinfo="skip",
        ),
        row=r + 1, col=c + 1,
    )
    fig4.add_trace(
        go.Scatter(
            x=sub.index, y=sub["pct"], mode="lines",
            line=dict(color=REGION_COLORS[region], width=2),
            name=region_label(region), showlegend=False,
            hovertemplate="%{x|%b %Y}<br>%{y:.1f}%<extra></extra>",
        ),
        row=r + 1, col=c + 1,
    )
fig4.update_yaxes(range=[50, 100], showgrid=True, gridcolor=GRID)
fig4.update_xaxes(showgrid=False)
fig4.update_layout(
    height=220 * rows, margin=dict(l=10, r=10, t=40, b=10),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK_MUTED, size=11),
    legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
)
st.plotly_chart(fig4, width="stretch")

st.divider()

# --- Trust-level drill-down ---
st.subheader("Trust drill-down")
trust_options = (
    filtered[["org_code", "org_name"]]
    .drop_duplicates(subset="org_code", keep="last")
    .sort_values("org_name")
)
trust_name_map = dict(zip(trust_options["org_code"], trust_options["org_name"]))
trust_choice = st.selectbox(
    "Select a trust",
    options=trust_options["org_code"],
    format_func=lambda code: trust_name_map[code],
    key="trust_select",
)

trust_df = filtered[filtered["org_code"] == trust_choice].sort_values("period")
trust_name = trust_df["org_name"].iloc[0]
trust_region = trust_df["region"].iloc[0]
trust_latest = trust_df[trust_df["period"] == latest_period]

if not trust_latest.empty:
    t_pct = 100 * trust_latest["in_4_hours"].iloc[0] / trust_latest["total_attendances"].iloc[0]
    rank_df = (
        filtered[filtered["period"] == latest_period]
        .assign(pct=lambda d: 100 * d["in_4_hours"] / d["total_attendances"])
        .sort_values("pct")
        .reset_index(drop=True)
    )
    rank = rank_df.index[rank_df["org_code"] == trust_choice][0] + 1
    tcol1, tcol2, tcol3 = st.columns(3)
    tcol1.metric(f"{trust_name} - % in 4hrs ({latest_period:%b %Y})", f"{t_pct:.1f}%")
    tcol2.metric("Region", region_label(trust_region))
    tcol3.metric("Rank (worst=1)", f"{rank} / {len(rank_df)}")

fig5 = go.Figure()
fig5.add_trace(
    go.Scatter(
        x=national.index, y=national["pct"], mode="lines",
        line=dict(color=CONTEXT_GRAY, width=1.5, dash="dot"),
        name="England average",
        hovertemplate="England avg %{x|%b %Y}: %{y:.1f}%<extra></extra>",
    )
)
fig5.add_trace(
    go.Scatter(
        x=trust_df["period"],
        y=100 * trust_df["in_4_hours"] / trust_df["total_attendances"],
        mode="lines+markers",
        line=dict(color=ACCENT, width=2), marker=dict(size=6, color=ACCENT),
        name=trust_name,
        hovertemplate=f"{trust_name} %{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
    )
)
fig5.add_hline(y=TARGET_PCT, line_dash="dash", line_color=INK_MUTED, line_width=1)
fig5.update_yaxes(title="% in 4 hours", range=[0, 100])
base_layout(fig5)
st.plotly_chart(fig5, width="stretch")

st.divider()

# --- Leaderboard table ---
st.subheader(f"All trusts ({latest_period:%B %Y})")
leaderboard = (
    filtered[filtered["period"] == latest_period]
    .assign(pct_in_4_hours=lambda d: (100 * d["in_4_hours"] / d["total_attendances"]).round(1))
    .loc[:, ["org_name", "region", "total_attendances", "in_4_hours", "pct_in_4_hours"]]
    .assign(region=lambda d: d["region"].map(region_label))
    .sort_values("pct_in_4_hours")
    .rename(columns={
        "org_name": "Trust", "region": "Region",
        "total_attendances": "Attendances", "in_4_hours": "In 4 hrs",
        "pct_in_4_hours": "% in 4 hrs",
    })
)
st.dataframe(leaderboard, width="stretch", hide_index=True)

st.caption(
    "total_attendances / in_4_hours are derived from six raw sub-categories, not published "
    "directly - see the Methodology section in the README for details and limitations."
)
