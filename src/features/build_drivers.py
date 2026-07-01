"""
Assemble the half-hourly *driver table* for the spike decomposition, and a
per-day evening-peak aggregation.

Two modes, auto-detected:

  PROXY  (always available) — uses the data reused from the sister forecast
         repo: imbalance price + NIV, Open-Meteo weather (temp / wind speed /
         solar irradiance), and the Carbon-Intensity wind share. Covers the
         H2 (solar drop-off) and H3 (low wind) mechanisms via proxies, plus a
         temperature term standing in for H1/H4.

  FULL   (when this repo's own data/raw has demand_outturn.csv AND
         generation_fuelhh.csv, produced by fetch_demand.py / fetch_fuelhh.py)
         — adds ABSOLUTE net demand (indo - wind), its evening ramp, a thermal
         margin proxy and interconnector net import, enabling the H1 and H5
         mechanisms directly rather than by proxy.

Keyed on (settlement_date, settlement_period) on the UK-local clock, identical
to the sister repo so everything joins.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import forecast_raw, DATA_RAW  # noqa: E402

UK_TZ = "Europe/London"
SUMMER_MONTHS = (6, 7, 8)
EVENING_SPS = list(range(35, 39))    # 17:00-19:00; 18:00 spike ~ SP36/37
MIDDAY_SPS = list(range(23, 29))     # 11:00-14:00; peak solar to be lost
RAMP_FROM_SP = 30                    # ~14:30, start of the evening net-demand ramp


# ── Base series (reused sister-repo data) ─────────────────────────────────────

def _load_prices(raw: Path) -> pd.DataFrame:
    f = raw / "system_prices_5yr.csv"
    if not f.exists():
        f = raw / "system_prices.csv"
    df = pd.read_csv(f, usecols=lambda c: c in {
        "settlement_date", "settlement_period", "ssp", "net_imbalance_volume"})
    df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.strftime("%Y-%m-%d")
    df["settlement_period"] = df["settlement_period"].astype(int)
    df = df.rename(columns={"ssp": "imbalance_price"})
    df["abs_niv"] = df["net_imbalance_volume"].abs()
    return df


def _load_weather(raw: Path) -> pd.DataFrame:
    w = pd.read_csv(raw / "weather_uk.csv")
    w["datetime_utc"] = pd.to_datetime(w["datetime_utc"], utc=True)
    w = w.set_index("datetime_utc").resample("30min").ffill().reset_index()
    uk = w["datetime_utc"].dt.tz_convert(UK_TZ)
    w["settlement_date"] = uk.dt.strftime("%Y-%m-%d")
    w["settlement_period"] = uk.dt.hour * 2 + uk.dt.minute // 30 + 1
    return w[["settlement_date", "settlement_period", "temp_c", "wind_ms", "solar_wm2"]]


def _load_gen_mix(raw: Path) -> pd.DataFrame:
    f = raw / "generation_mix.csv"
    if not f.exists():
        return pd.DataFrame(columns=["settlement_date", "settlement_period", "wind_pct"])
    g = pd.read_csv(f, usecols=["settlement_date", "settlement_period", "wind_pct"])
    g["settlement_date"] = pd.to_datetime(g["settlement_date"]).dt.strftime("%Y-%m-%d")
    return g


# ── Optional absolute-MW series (this repo's own fetchers) ─────────────────────

def _load_full_mw(local_raw: Path) -> pd.DataFrame | None:
    demand_f = local_raw / "demand_outturn.csv"
    fuel_f = local_raw / "generation_fuelhh.csv"
    if not (demand_f.exists() and fuel_f.exists()):
        return None
    d = pd.read_csv(demand_f)
    g = pd.read_csv(fuel_f)
    frames = [d, g]
    # Embedded solar (PV_Live) is optional but preferred — it completes net demand.
    solar_f = local_raw / "solar_pvlive.csv"
    solar = pd.read_csv(solar_f) if solar_f.exists() else None
    if solar is not None:
        frames.append(solar)
    for df in frames:
        df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.strftime("%Y-%m-%d")
    m = d.merge(g, on=["settlement_date", "settlement_period"], how="inner")
    if solar is not None:
        m = m.merge(solar, on=["settlement_date", "settlement_period"], how="left")
    # Absolute net demand = demand - wind - solar. Wind here is transmission-metered
    # (FUELHH); solar is PV_Live embedded outturn when present, else omitted (the
    # irradiance proxy then still carries H2 in the day-level aggregation).
    if {"indo_mw", "wind_mw"}.issubset(m.columns):
        m["net_demand_mw"] = m["indo_mw"] - m["wind_mw"]
        if "solar_mw" in m.columns:
            m["net_demand_mw"] = m["net_demand_mw"] - m["solar_mw"].fillna(0)
    thermal = [c for c in ("ccgt_mw", "coal_mw", "biomass_mw", "ocgt_mw", "oil_mw")
               if c in m.columns]
    if thermal and "total_generation_mw" in m.columns:
        # crude headroom proxy: how much of supply is leaning on dispatchable thermal
        m["thermal_share"] = m[thermal].sum(axis=1) / m["total_generation_mw"].replace(0, np.nan)
    return m


# ── Public API ────────────────────────────────────────────────────────────────

def build_sp_table() -> tuple[pd.DataFrame, str]:
    """Half-hourly driver table. Returns (df, mode) where mode in {'proxy','full'}."""
    raw = forecast_raw()
    df = (
        _load_prices(raw)
        .merge(_load_weather(raw), on=["settlement_date", "settlement_period"], how="inner")
        .merge(_load_gen_mix(raw), on=["settlement_date", "settlement_period"], how="left")
    )
    mode = "proxy"
    full = _load_full_mw(DATA_RAW)
    if full is not None:
        df = df.merge(full, on=["settlement_date", "settlement_period"], how="left")
        mode = "full"
    df["month"] = pd.to_datetime(df["settlement_date"]).dt.month
    return df, mode


def evening_peak_by_day(sp: pd.DataFrame, summer_only: bool = True) -> pd.DataFrame:
    """Collapse to one row per day with evening-peak drivers + spike target.

    Target:
        price_eve       mean imbalance price over the evening peak (SP35-38)
    Proxy drivers:
        wind_share_eve  mean wind % over the peak              (H3, lower=tighter)
        temp_max        daily max temperature                  (H1 demand / H4 derate)
        solar_midday    mean midday irradiance (the solar later lost)  (H2)
        niv_eve         mean |NIV| over the peak               (volume control)
    Full-mode extra drivers (added when present):
        netdem_ramp     net-demand rise from SP30 -> peak      (H1)
        netdem_eve      net demand at the peak                 (H1 level)
        ic_import_eve   interconnector net import at the peak  (H5, higher=looser)
        thermal_share_eve                                       (H4)
    """
    d = sp.copy()
    if summer_only:
        d = d[d["month"].isin(SUMMER_MONTHS)]

    eve = d[d["settlement_period"].isin(EVENING_SPS)]
    mid = d[d["settlement_period"].isin(MIDDAY_SPS)]

    g = eve.groupby("settlement_date")
    out = pd.DataFrame({
        "price_eve": g["imbalance_price"].mean(),
        "niv_eve": g["abs_niv"].mean(),
        "temp_eve": g["temp_c"].mean(),
        "wind_share_eve": g["wind_pct"].mean() if "wind_pct" in eve else np.nan,
        "wind_ms_eve": g["wind_ms"].mean(),
    })
    out["temp_max"] = d.groupby("settlement_date")["temp_c"].max()
    out["solar_midday"] = mid.groupby("settlement_date")["solar_wm2"].mean()

    if "net_demand_mw" in d.columns:
        nd = d.groupby(["settlement_date", "settlement_period"])["net_demand_mw"].mean().reset_index()
        piv = nd.pivot(index="settlement_date", columns="settlement_period", values="net_demand_mw")
        peak_cols = [c for c in EVENING_SPS if c in piv.columns]
        if RAMP_FROM_SP in piv.columns and peak_cols:
            out["netdem_eve"] = piv[peak_cols].mean(axis=1)
            out["netdem_ramp"] = piv[peak_cols].mean(axis=1) - piv[RAMP_FROM_SP]
    if "interconnector_net_mw" in d.columns:
        out["ic_import_eve"] = eve.groupby("settlement_date")["interconnector_net_mw"].mean()
    if "thermal_share" in d.columns:
        out["thermal_share_eve"] = eve.groupby("settlement_date")["thermal_share"].mean()

    return out.dropna(subset=["price_eve"]).reset_index()


if __name__ == "__main__":
    sp, mode = build_sp_table()
    day = evening_peak_by_day(sp)
    print(f"mode={mode}  sp_rows={len(sp):,}  summer_days={len(day)}")
    print("driver columns:", [c for c in day.columns if c != "settlement_date"])
    print(day.describe().round(1).to_string())
