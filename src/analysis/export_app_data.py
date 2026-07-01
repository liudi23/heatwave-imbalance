"""
Precompute the bundled data the Streamlit presentation app reads, so the app
is portable (no live API, no sister-repo path, no recomputation at runtime).

Writes into app/data/:
    diurnal.csv       per-SP mean profile, hot vs mild summer days
                      (imbalance_price, abs_niv, temp_c, wind_pct, solar_wm2)
    attribution.csv   driver | hypothesis | coef_gbp_per_sd | t | spearman_r
    binned.csv        decile partial relationships (driver, x, price) per driver
    summary.json      headline numbers + provenance

Run (in an env with the sister-repo data available):
    UK_FORECAST_REPO=/path/to/uk-system-price-forecast \
        python src/analysis/export_app_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import REPO_ROOT  # noqa: E402
from src.features.build_drivers import (  # noqa: E402
    build_sp_table, evening_peak_by_day, SUMMER_MONTHS, EVENING_SPS,
)
from src.analysis.spike_decomposition import (  # noqa: E402
    select_drivers, standardise, ols,
)

APP_DATA = REPO_ROOT / "app" / "data"
HOT_Q, MILD_Q = 0.80, 0.40


def classify(sp: pd.DataFrame) -> pd.DataFrame:
    summer = sp[sp["month"].isin(SUMMER_MONTHS)]
    dmax = summer.groupby("settlement_date")["temp_c"].max()
    hot_t, mild_t = dmax.quantile(HOT_Q), dmax.quantile(MILD_Q)
    regime = np.where(dmax >= hot_t, "hot", np.where(dmax <= mild_t, "mild", "other"))
    reg = pd.DataFrame({"settlement_date": dmax.index, "regime": regime})
    return reg, float(hot_t), float(mild_t)


def main() -> None:
    sp, mode = build_sp_table()
    reg, hot_t, mild_t = classify(sp)

    summer = sp[sp["month"].isin(SUMMER_MONTHS)].merge(reg, on="settlement_date")
    keep = summer[summer["regime"].isin(["hot", "mild"])]

    # 1. Diurnal profile
    diurnal = (
        keep.groupby(["regime", "settlement_period"])
        .agg(imbalance_price=("imbalance_price", "mean"),
             abs_niv=("abs_niv", "mean"),
             temp_c=("temp_c", "mean"),
             wind_pct=("wind_pct", "mean"),
             solar_wm2=("solar_wm2", "mean"))
        .reset_index()
    )
    diurnal["hour"] = (diurnal["settlement_period"] - 1) / 2.0

    # 2. Attribution (re-fit, same as spike_decomposition)
    day = evening_peak_by_day(sp)
    drivers = select_drivers(day.columns, mode)
    cols = list(drivers)
    d = day.dropna(subset=cols + ["price_eve"]).copy()
    Xs = np.column_stack([standardise(d[c]).values for c in cols])
    beta, se, tstat, r2 = ols(Xs, d["price_eve"].values)

    attribution = pd.DataFrame([{
        "driver": drivers[c][0], "hypothesis": drivers[c][1],
        "coef_gbp_per_sd": beta[i + 1], "t": tstat[i + 1],
        "spearman_r": d[[c, "price_eve"]].corr(method="spearman").iloc[0, 1],
    } for i, c in enumerate(cols)]).sort_values(
        "coef_gbp_per_sd", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)

    # 3. Binned partial relationships
    binned_rows = []
    for c in cols:
        dd = d[[c, "price_eve"]].dropna()
        q = pd.qcut(dd[c], 10, duplicates="drop")
        grp = dd.groupby(q, observed=True).agg(x=(c, "mean"), price=("price_eve", "mean"))
        for _, r in grp.iterrows():
            binned_rows.append({"driver": drivers[c][0], "x": r["x"], "price": r["price"]})
    binned = pd.DataFrame(binned_rows)

    # 4. Headline summary
    ev = [s for s in EVENING_SPS if s in diurnal["settlement_period"].unique()]
    piv = diurnal.pivot(index="settlement_period", columns="regime", values="imbalance_price")
    npiv = diurnal.pivot(index="settlement_period", columns="regime", values="abs_niv")
    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": mode,
        "date_range": [sp["settlement_date"].min(), sp["settlement_date"].max()],
        "n_summer_days": int(reg["regime"].isin(["hot", "mild"]).sum()),
        "n_attribution_days": int(len(d)),
        "hot_threshold_c": round(hot_t, 1),
        "mild_threshold_c": round(mild_t, 1),
        "evening_price_uplift": round(float(piv.loc[ev, "hot"].mean()
                                            - piv.loc[ev, "mild"].mean()), 1),
        "evening_niv_uplift": round(float(npiv.loc[ev, "hot"].mean()
                                          - npiv.loc[ev, "mild"].mean()), 1),
        "model_r2": round(float(r2), 3),
    }

    APP_DATA.mkdir(parents=True, exist_ok=True)
    diurnal.to_csv(APP_DATA / "diurnal.csv", index=False)
    attribution.to_csv(APP_DATA / "attribution.csv", index=False)
    binned.to_csv(APP_DATA / "binned.csv", index=False)
    (APP_DATA / "summary.json").write_text(json.dumps(summary, indent=2))
    print("Wrote bundled app data ->", APP_DATA)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
