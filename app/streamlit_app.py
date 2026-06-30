"""
heatwave-Imbalance — results presentation (read-only).

Renders the precomputed findings bundled in app/data/ (no live API, no
sister-repo dependency). Regenerate that bundle with:
    python src/analysis/export_app_data.py

Run:
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA = Path(__file__).resolve().parent / "data"
HOT, MILD = "#c0392b", "#2980b9"
REPO_URL = "https://github.com/liudi23/heatwave-imbalance"


@st.cache_data
def load():
    diurnal = pd.read_csv(DATA / "diurnal.csv")
    attribution = pd.read_csv(DATA / "attribution.csv")
    binned = pd.read_csv(DATA / "binned.csv")
    summary = json.loads((DATA / "summary.json").read_text())
    return diurnal, attribution, binned, summary


st.set_page_config(page_title="Heatwave stress on GB balancing",
                   page_icon="🌡️", layout="wide")

diurnal, attribution, binned, summary = load()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🌡️ How heat stresses the GB balancing system")
st.caption("Climate-resilience analysis of the imbalance (cash-out) price and the "
           "~18:00 evening spike — understanding the physical drivers, not predicting price.")

d0, d1 = summary["date_range"]
st.markdown(
    f"**Hot vs mild summer days, {d0[:4]}–{d1[:4]}.** A *hot* day = daily-max temperature "
    f"in the top 20% of summer days (population-weighted national ≥ {summary['hot_threshold_c']} °C); "
    f"*mild* = bottom 40% (≤ {summary['mild_threshold_c']} °C)."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Evening price uplift", f"+£{summary['evening_price_uplift']:.0f}/MWh",
          help="Hot vs mild, mean over the evening peak SP35–38 (~17:00–19:00).")
c2.metric("Evening |NIV| uplift", f"+{summary['evening_niv_uplift']:.0f} MWh",
          help="Net imbalance volume barely moves — a pricing effect, not a volume one.")
c3.metric("Attribution R²", f"{summary['model_r2']:.2f}",
          help="Share of day-to-day variation in evening price explained by the proxy drivers.")
c4.metric("Mode", summary["mode"].upper(),
          help="PROXY = wind share / irradiance / temp. FULL adds absolute net-demand "
               "ramp (H1) & interconnectors (H5) once that MW data is fetched.")

st.divider()

# ── Headline finding ─────────────────────────────────────────────────────────
st.markdown(
    "### The finding\n"
    "On hot evenings the imbalance price carries a large premium that **|NIV| does not "
    "explain** — it looks like tight-margin scarcity pricing rather than a volume effect. "
    "Two robust drivers stand out: **higher temperature** and **lower wind share** — the "
    "anticyclonic-heat signature (hot, still evenings into the duck-curve peak)."
)

# ── Diurnal profiles ─────────────────────────────────────────────────────────
st.subheader("Diurnal profile — hot vs mild summer days")
series = {
    "Imbalance price (£/MWh)": "imbalance_price",
    "System imbalance |NIV| (MWh)": "abs_niv",
    "Temperature (°C)": "temp_c",
    "Wind share (%)": "wind_pct",
    "Solar irradiance (W/m²)": "solar_wm2",
}
choice = st.selectbox("Series", list(series), index=0)
col = series[choice]
piv = diurnal.pivot(index="hour", columns="regime", values=col).reset_index()
fig = go.Figure()
fig.add_vrect(x0=17, x1=19, fillcolor="orange", opacity=0.12, line_width=0,
              annotation_text="evening peak", annotation_position="top left")
fig.add_trace(go.Scatter(x=piv["hour"], y=piv["hot"], name="hot days",
                         line=dict(color=HOT, width=3)))
fig.add_trace(go.Scatter(x=piv["hour"], y=piv["mild"], name="mild days",
                         line=dict(color=MILD, width=3)))
fig.update_layout(height=420, xaxis_title="hour of day (UK local)", yaxis_title=choice,
                  margin=dict(t=30), legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Driver attribution ───────────────────────────────────────────────────────
st.subheader("What drives the evening spike? — driver attribution")
left, right = st.columns([3, 2])

with left:
    a = attribution.sort_values("coef_gbp_per_sd")
    bar = go.Figure(go.Bar(
        x=a["coef_gbp_per_sd"], y=a["driver"], orientation="h",
        marker_color=[HOT if v > 0 else MILD for v in a["coef_gbp_per_sd"]],
        text=[f"{v:+.0f}" for v in a["coef_gbp_per_sd"]], textposition="outside",
        customdata=a[["hypothesis"]], hovertemplate="%{y}<br>%{customdata[0]}<br>"
                                                     "%{x:+.1f} £/MWh per SD<extra></extra>"))
    bar.update_layout(height=360, xaxis_title="£/MWh per +1 SD of driver (partial)",
                      margin=dict(t=10, l=10))
    st.plotly_chart(bar, use_container_width=True)
    st.caption("Standardised OLS coefficients: £/MWh change in evening price per 1 SD of "
               "each driver, holding the others fixed.")

with right:
    show = attribution.rename(columns={
        "coef_gbp_per_sd": "£/MWh per SD", "spearman_r": "Spearman r", "t": "t-stat"})
    st.dataframe(
        show.style.format({"£/MWh per SD": "{:+.1f}", "t-stat": "{:+.1f}",
                           "Spearman r": "{:+.2f}"}),
        hide_index=True, use_container_width=True)

# ── Partial relationships ────────────────────────────────────────────────────
st.subheader("Partial relationships (binned)")
drv = st.selectbox("Driver", attribution["driver"].tolist(), index=0)
b = binned[binned["driver"] == drv]
line = px.line(b, x="x", y="price", markers=True)
line.update_traces(line_color=HOT)
line.update_layout(height=340, xaxis_title=drv, yaxis_title="evening price (£/MWh)",
                   margin=dict(t=10))
st.plotly_chart(line, use_container_width=True)

# ── Caveats ──────────────────────────────────────────────────────────────────
with st.expander("Method & honest caveats"):
    st.markdown(
        f"- **Scope:** GB summer days (Jun–Aug), {d0}–{d1}; "
        f"{summary['n_attribution_days']} days in the attribution.\n"
        "- **Interpretability-first:** a transparent standardised OLS, not a black-box "
        "predictor — the goal is to *rank drivers*, not maximise fit.\n"
        f"- **R² ≈ {summary['model_r2']:.2f}:** the proxies explain ~21% of day-to-day "
        "variation; evening spikes are tail/margin events these proxies don't fully capture.\n"
        "- **Solar sign:** midday solar flips between univariate (~0) and partial (−) because "
        "the proxy can't separate solar *level* from *drop-off*.\n"
        "- **Next:** running `fetch_demand`/`fetch_fuelhh` adds absolute net-demand ramp (H1) "
        "and interconnector imports (H5), upgrading the app to **full mode**."
    )

st.caption(f"Source: precomputed bundle ({summary['mode']} mode), generated "
           f"{summary['generated_at']}.  Code & data: {REPO_URL}")
