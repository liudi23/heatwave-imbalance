# heatwave-Imbalance

**How extreme heat stresses the GB balancing system — and what it means for a decarbonising grid.**

A climate-resilience analysis of the GB electricity imbalance (cash-out) price and Net Imbalance Volume (NIV) under hot weather, with a focus on the recurring **~18:00 evening price spikes**. The emphasis is on *understanding and ranking the physical drivers* of those spikes, not predicting them — see [`PHASE1_SCOPE.md`](PHASE1_SCOPE.md) for the full framing and the five hypotheses (H1–H5).

This project is a deliberate companion to **`uk-system-price-forecast`** and reuses its data and conventions (see [Compatibility](#compatibility)).

## First finding (real data, 2021–2026)

Across five summers, on the **hottest 20% of days** the imbalance price in the evening peak (≈17:00–19:00, SP35–38) is on average **~£77/MWh higher** than on mild summer days — yet average **|NIV| is essentially unchanged**. So at the national level the heat-related evening premium looks like a **scarcity-pricing / marginal-action-cost effect more than a volume effect**. The same hot days show **lower wind share** and **higher midday solar that collapses into the peak** — early support for H3 (low wind under anticyclonic heat) and H2 (solar drop-off).

![Heatwave diurnal profile](figures/heatwave_diurnal_profile.png)

> Caveat: at a population-weighted *national* level the hottest summer quintile tops out near ~21 °C, so this first cut uses a percentile "hot day" label. The strict Met Office heatwave definition (≥3 consecutive days over a regional absolute threshold) and the absolute net-demand decomposition come with the demand/FUELHH data (next step).

## Layout
```
PHASE1_SCOPE.md            project framing, hypotheses, method, deliverables
docs/DATA_SOURCES.md       confirmed BMRS dataset IDs / endpoints
src/config.py              paths; resolves the sister forecast repo for reuse
src/timeutils.py           UK settlement-time helpers (shared with forecast repo)
src/data/_http.py          retry/backoff + record parsing (house style)
src/data/fetch_elexon.py   imbalance price + NIV   (vendored from forecast repo)
src/data/fetch_weather.py  Open-Meteo UK weather   (vendored from forecast repo)
src/data/fetch_demand.py   NEW — INDO/ITSDO demand outturn (MW)
src/data/fetch_fuelhh.py   NEW — generation by fuel + interconnectors (MW)
src/analysis/heatwave_diurnal.py   anchor figure: hot vs mild diurnal profiles
figures/                   generated figures
data/raw, data/processed   local datasets (gitignored)
```

## Quickstart

**Standalone** (no sister repo needed — fetch everything from open APIs):
```bash
pip install -r requirements.txt
python src/data/fetch_elexon.py   --start 2021-06-01 --end 2026-08-31   # price + NIV
python src/data/fetch_weather.py  --start 2021-06-01 --end 2026-08-31   # UK weather
python src/data/fetch_demand.py   --start 2022-06-01 --end 2022-08-31   # demand (MW)
python src/data/fetch_fuelhh.py   --start 2022-06-01 --end 2022-08-31   # gen by fuel (MW)
python src/analysis/heatwave_diurnal.py                                  # anchor figure
```

**Reuse** the sister repo's already-downloaded data instead of re-fetching:
```bash
export UK_FORECAST_REPO=/path/to/uk-system-price-forecast
python src/analysis/heatwave_diurnal.py
```
`src/config.forecast_raw()` prefers the sister repo if `UK_FORECAST_REPO` is set (or it sits in `../uk-system-price-forecast`), and otherwise falls back to this repo's own `data/raw/`.

## Compatibility
Same `(settlement_date, settlement_period)` key, same UK-local SP convention, same retry/append/CLI fetcher pattern as `uk-system-price-forecast`. This project **reads that repo's** `system_prices_5yr.csv`, `weather_uk.csv` and `generation_mix.csv` directly (via `src/config.forecast_raw()`) and **adds** absolute-MW demand, generation-by-fuel and interconnector tables on top — so the new physical-driver series can flow back into the forecasting pipeline later if useful.

## Status
Phase 1, in progress. Done: scope, reuse scaffolding, two new BMRS fetchers, anchor figure. Next: pull demand + FUELHH for the heatwave windows, build absolute net demand, decompose the evening spike across H1–H5, and write the short public writeup.
