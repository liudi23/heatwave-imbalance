"""
Anchor analysis: how do heatwave days reshape the GB imbalance-price and
NIV diurnal profile, and is the ~18:00 (SP 36-37) evening spike amplified?

Reuses the sister forecast repo's raw data (system prices + NIV + weather)
via src.config, so no re-fetching is needed for this first cut. Absolute
net-demand decomposition (demand / wind / solar in MW) is added in a later
step once fetch_demand.py / fetch_fuelhh.py have been run.

Method (interpretability-first, no model):
  * Restrict to summer settlement days (Jun-Aug).
  * Classify each UK-local day by its population-weighted daily-max temp:
      - "heatwave"     = daily max in the top quintile of summer days
      - "mild summer"  = daily max in the bottom 40% of summer days
  * Compare the mean diurnal profile of imbalance price and |NIV| across the
    two regimes, and overlay the temperature / wind-share / solar-irradiance
    profiles that tell the duck-curve + low-wind story.

Output: figures/heatwave_diurnal_profile.png  and a small printed summary.

Usage:
    python src/analysis/heatwave_diurnal.py
    UK_FORECAST_REPO=/path/to/uk-system-price-forecast python src/analysis/heatwave_diurnal.py
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
from src.config import forecast_raw, FIGURES  # noqa: E402

UK_TZ = "Europe/London"
SUMMER_MONTHS = (6, 7, 8)
HOT_QUANTILE = 0.80    # daily-max temp >= this quantile  -> heatwave regime
MILD_QUANTILE = 0.40   # daily-max temp <= this quantile  -> mild-summer regime
EVENING_SPS = range(35, 39)   # SP35-38  ~ 17:00-19:00 local; 18:00 ~ SP36/37


# ── Loading & SP alignment ────────────────────────────────────────────────────

def load_prices(raw: Path) -> pd.DataFrame:
    """5-year system prices: imbalance price (ssp) + NIV, keyed on (date, SP)."""
    f = raw / "system_prices_5yr.csv"
    if not f.exists():
        f = raw / "system_prices.csv"
    df = pd.read_csv(f, usecols=lambda c: c in {
        "settlement_date", "settlement_period", "ssp", "net_imbalance_volume",
    })
    df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.strftime("%Y-%m-%d")
    df["settlement_period"] = df["settlement_period"].astype(int)
    df = df.rename(columns={"ssp": "imbalance_price"})
    df["abs_niv"] = df["net_imbalance_volume"].abs()
    return df


def load_weather_sp(raw: Path) -> pd.DataFrame:
    """Hourly UK weather -> (settlement_date, settlement_period) on UK-local clock.

    Each UTC hour maps to two 30-min settlement periods; we forward-fill the
    hourly series onto the 30-min grid before deriving the SP index, matching
    the sister repo's SP convention (SP = hour*2 + minute//30 + 1, UK-local).
    """
    w = pd.read_csv(raw / "weather_uk.csv")
    w["datetime_utc"] = pd.to_datetime(w["datetime_utc"], utc=True)
    w = w.set_index("datetime_utc").resample("30min").ffill().reset_index()
    uk = w["datetime_utc"].dt.tz_convert(UK_TZ)
    w["settlement_date"] = uk.dt.strftime("%Y-%m-%d")
    w["settlement_period"] = uk.dt.hour * 2 + uk.dt.minute // 30 + 1
    return w[["settlement_date", "settlement_period", "temp_c", "wind_ms", "solar_wm2"]]


def load_generation(raw: Path) -> pd.DataFrame:
    f = raw / "generation_mix.csv"
    if not f.exists():
        return pd.DataFrame(columns=["settlement_date", "settlement_period", "wind_pct"])
    g = pd.read_csv(f, usecols=["settlement_date", "settlement_period", "wind_pct"])
    g["settlement_date"] = pd.to_datetime(g["settlement_date"]).dt.strftime("%Y-%m-%d")
    return g


# ── Heatwave classification ───────────────────────────────────────────────────

def classify_days(weather_sp: pd.DataFrame) -> pd.DataFrame:
    """Per summer day: daily-max temp and a regime label (heatwave/mild/other)."""
    daily = (
        weather_sp.assign(month=lambda d: pd.to_datetime(d["settlement_date"]).dt.month)
        .query("month in @SUMMER_MONTHS")
        .groupby("settlement_date", as_index=False)["temp_c"].max()
        .rename(columns={"temp_c": "daily_max_temp"})
    )
    hot = daily["daily_max_temp"].quantile(HOT_QUANTILE)
    mild = daily["daily_max_temp"].quantile(MILD_QUANTILE)
    # Labelled "hot" / "mild" rather than "heatwave": at a population-weighted
    # NATIONAL level even a 32C London day averages down, so the top summer
    # quintile tops out near ~21C. The strict Met Office heatwave definition
    # (>=3 consecutive days over a regional absolute threshold) is applied in
    # the later regional/demand-decomposition step, not here.
    daily["regime"] = np.where(
        daily["daily_max_temp"] >= hot, "hot (top 20%)",
        np.where(daily["daily_max_temp"] <= mild, "mild summer", "other"),
    )
    daily.attrs["hot_threshold"] = hot
    daily.attrs["mild_threshold"] = mild
    return daily


# ── Diurnal aggregation ───────────────────────────────────────────────────────

def diurnal(df: pd.DataFrame, value: str) -> pd.DataFrame:
    return (
        df.groupby(["regime", "settlement_period"], as_index=False)[value]
        .mean()
        .pivot(index="settlement_period", columns="regime", values=value)
    )


def main() -> None:
    raw = forecast_raw()
    prices = load_prices(raw)
    weather = load_weather_sp(raw)
    gen = load_generation(raw)

    days = classify_days(weather)
    keep = days.query("regime in ['hot (top 20%)', 'mild summer']")

    df = (
        prices.merge(weather, on=["settlement_date", "settlement_period"], how="inner")
        .merge(gen, on=["settlement_date", "settlement_period"], how="left")
        .merge(keep[["settlement_date", "regime"]], on="settlement_date", how="inner")
    )

    n_hw = days.query("regime=='hot (top 20%)'").shape[0]
    n_mild = days.query("regime=='mild summer'").shape[0]
    print(f"Summer days: {len(days)}  | heatwave={n_hw} (max>= {days.attrs['hot_threshold']:.1f}C)"
          f"  mild={n_mild} (max<= {days.attrs['mild_threshold']:.1f}C)")

    sp_to_hour = lambda sp: (sp - 1) / 2.0
    price_d = diurnal(df, "imbalance_price")
    niv_d = diurnal(df, "abs_niv")
    temp_d = diurnal(df, "temp_c")
    wind_d = diurnal(df, "wind_pct") if "wind_pct" in df else None
    solar_d = diurnal(df, "solar_wm2")

    # Evening-peak uplift summary
    ev = [sp for sp in EVENING_SPS if sp in price_d.index]
    hot_col = "hot (top 20%)"
    up_price = price_d.loc[ev, hot_col].mean() - price_d.loc[ev, "mild summer"].mean()
    up_niv = niv_d.loc[ev, hot_col].mean() - niv_d.loc[ev, "mild summer"].mean()
    print(f"Evening peak (SP{ev[0]}-{ev[-1]}): imbalance-price uplift "
          f"hot vs mild = +{up_price:.1f} GBP/MWh ; |NIV| uplift = +{up_niv:.0f} MWh")

    # ── Plot ──────────────────────────────────────────────────────────────────
    hours = [sp_to_hour(sp) for sp in price_d.index]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
    C_HW, C_MILD = "#c0392b", "#2980b9"

    def style(ax, title, ylab):
        ax.set_title(title, fontsize=11, weight="bold")
        ax.set_ylabel(ylab)
        ax.axvspan(17, 19, color="orange", alpha=0.10)
        ax.grid(alpha=0.25)

    ax = axes[0, 0]
    ax.plot(hours, price_d["hot (top 20%)"], color=C_HW, lw=2, label="hot days (top 20%)")
    ax.plot(hours, price_d["mild summer"], color=C_MILD, lw=2, label="mild summer")
    style(ax, "Imbalance price — diurnal profile", "GBP/MWh")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    ax.plot(hours, niv_d["hot (top 20%)"], color=C_HW, lw=2)
    ax.plot(hours, niv_d["mild summer"], color=C_MILD, lw=2)
    style(ax, "System imbalance volume |NIV|", "MWh")

    ax = axes[1, 0]
    ax.plot(hours, temp_d["hot (top 20%)"], color=C_HW, lw=2)
    ax.plot(hours, temp_d["mild summer"], color=C_MILD, lw=2)
    style(ax, "Temperature", "deg C")
    ax.set_xlabel("hour of day (UK local)")

    ax = axes[1, 1]
    if wind_d is not None:
        ax.plot(hours, wind_d["hot (top 20%)"], color=C_HW, lw=2, label="wind % (hot)")
        ax.plot(hours, wind_d["mild summer"], color=C_MILD, lw=2, label="wind % (mild)")
        ax.set_ylabel("wind share %")
    ax2 = ax.twinx()
    ax2.plot(hours, solar_d["hot (top 20%)"], color=C_HW, lw=1.3, ls="--", alpha=0.8)
    ax2.plot(hours, solar_d["mild summer"], color=C_MILD, lw=1.3, ls="--", alpha=0.8)
    ax2.set_ylabel("solar irradiance W/m2 (dashed)")
    style(ax, "Wind share (solid) & solar (dashed)", "wind share %")
    ax.set_xlabel("hour of day (UK local)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    fig.suptitle(
        "GB balancing stress under heat: hot vs mild summer days "
        f"(Jun-Aug, 2021-2026)\nShaded band = evening peak ~17:00-19:00 (SP35-38)",
        fontsize=12, weight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    FIGURES.mkdir(parents=True, exist_ok=True)
    out = FIGURES / "heatwave_diurnal_profile.png"
    fig.savefig(out, dpi=140)
    print(f"Saved figure -> {out}")


if __name__ == "__main__":
    main()
