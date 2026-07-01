"""
Decompose the GB evening (~18:00) imbalance-price spike across the physical
drivers of hypotheses H1-H5 — interpretability-first, no black box.

For each summer day we take the evening-peak (SP35-38) mean imbalance price as
the target and regress it on standardised physical drivers. Because the drivers
are standardised, each coefficient reads as "GBP/MWh change in the evening price
per 1 standard-deviation move in that driver, holding the others fixed" — a
directly rankable attribution. We report alongside it the univariate Spearman
correlation, so collinearity (hot days are also low-wind, high-solar days) is
visible rather than hidden.

Drivers (proxy mode, available now):
    wind_share_eve  evening wind share %      H3  (low wind under anticyclonic heat)
    solar_midday    midday irradiance W/m2    H2  (solar later lost into the peak)
    temp_max        daily max temperature     H1/H4 (cooling demand / thermal derate)
    niv_eve         evening |NIV| MWh         volume control
Full mode adds, when the absolute-MW data is present:
    netdem_ramp     net-demand ramp SP30->peak  H1
    ic_import_eve   interconnector net import   H5

Output: figures/spike_decomposition.png  + printed attribution table.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import FIGURES  # noqa: E402
from src.features.build_drivers import build_sp_table, evening_peak_by_day  # noqa: E402

# Driver -> (pretty label, hypothesis). Order = display order.
PROXY_DRIVERS = {
    "wind_share_eve": ("Evening wind share", "H3 low wind"),
    "solar_midday":   ("Midday solar (to be lost)", "H2 solar drop-off"),
    "temp_max":       ("Daily max temperature", "H1/H4 demand & derate"),
    "niv_eve":        ("Evening |NIV|", "volume"),
}
FULL_EXTRA = {
    "netdem_ramp":   ("Net-demand ramp SP30->peak", "H1 net-demand ramp"),
    "ic_import_eve": ("Interconnector net import", "H5 imports"),
}
# In full mode, replace the irradiance proxy for H2 with the absolute solar
# drop-off (MW lost midday->peak) when it is available.
SOLAR_FULL = {"solar_dropoff_mw": ("Solar drop-off midday->peak", "H2 solar drop-off")}


def select_drivers(columns, mode: str) -> dict:
    """Driver dict for the given mode, restricted to columns that exist.

    Shared by the decomposition and the app-data export so both stay in sync.
    """
    drivers = dict(PROXY_DRIVERS)
    if mode == "full":
        if "solar_dropoff_mw" in columns:          # upgrade H2 proxy -> absolute
            drivers.pop("solar_midday", None)
            drivers.update(SOLAR_FULL)
        for k, v in FULL_EXTRA.items():
            if k in columns:
                drivers[k] = v
    return {c: drivers[c] for c in drivers if c in columns}


def standardise(x: pd.Series) -> pd.Series:
    return (x - x.mean()) / x.std(ddof=0)


def ols(X: np.ndarray, y: np.ndarray):
    """OLS with intercept. Returns (beta, se, tstat, r2). beta[0] = intercept."""
    n, k = X.shape
    Xi = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(Xi, y, rcond=None)
    resid = y - Xi @ beta
    dof = n - Xi.shape[1]
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.inv(Xi.T @ Xi)
    se = np.sqrt(np.diag(cov))
    tstat = beta / se
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / ss_tot
    return beta, se, tstat, r2


def main() -> None:
    sp, mode = build_sp_table()
    day = evening_peak_by_day(sp)

    drivers = select_drivers(day.columns, mode)
    cols = list(drivers)

    d = day.dropna(subset=cols + ["price_eve"]).copy()
    Xs = np.column_stack([standardise(d[c]).values for c in cols])
    y = d["price_eve"].values
    beta, se, tstat, r2 = ols(Xs, y)

    # Attribution table
    rows = []
    for i, c in enumerate(cols):
        spearman = d[[c, "price_eve"]].corr(method="spearman").iloc[0, 1]
        rows.append({
            "driver": drivers[c][0],
            "hypothesis": drivers[c][1],
            "coef_gbp_per_sd": beta[i + 1],
            "t": tstat[i + 1],
            "spearman_r": spearman,
        })
    tab = pd.DataFrame(rows).sort_values("coef_gbp_per_sd", key=lambda s: s.abs(),
                                         ascending=False).reset_index(drop=True)

    print(f"\nMode: {mode.upper()}   summer days n={len(d)}   model R^2={r2:.2f}")
    print("Evening-peak imbalance price (SP35-38) attribution:")
    print(tab.to_string(index=False, float_format=lambda v: f"{v:7.2f}"))
    print("\ncoef_gbp_per_sd = GBP/MWh change per +1 SD of the driver, others held fixed")

    # ── Figure ──────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(13, 8))
    gs = fig.add_gridspec(2, 3)

    # Panel A: standardized-coefficient ranking
    axA = fig.add_subplot(gs[:, 0])
    order = tab.iloc[::-1]
    labels = [f"{d}\n({h})" for d, h in zip(order["driver"], order["hypothesis"])]
    colors = ["#c0392b" if v > 0 else "#2980b9" for v in order["coef_gbp_per_sd"]]
    bars = axA.barh(labels, order["coef_gbp_per_sd"], color=colors)
    axA.axvline(0, color="k", lw=0.8)
    axA.set_title("Driver attribution\n(partial, GBP/MWh per 1 SD)", fontsize=11, weight="bold")
    axA.set_xlabel("GBP/MWh per SD")
    axA.margins(x=0.22)
    for bar, v in zip(bars, order["coef_gbp_per_sd"]):
        axA.text(v + (3 if v >= 0 else -3), bar.get_y() + bar.get_height() / 2,
                 f"{v:+.0f}", va="center", ha="left" if v >= 0 else "right",
                 fontsize=9, weight="bold", color="#333")
    axA.grid(axis="x", alpha=0.25)

    # Panels B-D: binned partial relationships for the top proxy mechanisms
    def binned(ax, col, label, color):
        dd = d[[col, "price_eve"]].dropna()
        q = pd.qcut(dd[col], 10, duplicates="drop")
        grp = dd.groupby(q, observed=True).agg(x=(col, "mean"), price=("price_eve", "mean"))
        ax.plot(grp["x"], grp["price"], "o-", color=color, lw=2)
        ax.set_title(label, fontsize=10, weight="bold")
        ax.set_ylabel("evening price GBP/MWh")
        ax.grid(alpha=0.25)

    binned(fig.add_subplot(gs[0, 1]), "wind_share_eve", "Price vs evening wind share (H3)", "#c0392b")
    binned(fig.add_subplot(gs[0, 2]), "temp_max", "Price vs daily max temp (H1/H4)", "#e67e22")
    binned(fig.add_subplot(gs[1, 1]), "solar_midday", "Price vs midday solar (H2)", "#16a085")
    axN = fig.add_subplot(gs[1, 2])
    binned(axN, "niv_eve", "Price vs evening |NIV| (volume)", "#7f8c8d")
    axN.set_xlabel("driver value")

    sub = ("proxy drivers — absolute net-demand ramp (H1) & interconnectors (H5) "
           "added when MW data is fetched" if mode == "proxy"
           else "full driver set incl. net-demand ramp (H1) & interconnectors (H5)")
    fig.suptitle(f"What drives the ~18:00 imbalance-price spike? GB summer days 2021-2026 "
                 f"(R^2={r2:.2f})\n{sub}", fontsize=12, weight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    FIGURES.mkdir(parents=True, exist_ok=True)
    out = FIGURES / "spike_decomposition.png"
    fig.savefig(out, dpi=140)
    print(f"\nSaved figure -> {out}")


if __name__ == "__main__":
    main()
