# Data sources — confirmed datasets & endpoints

All half-hourly tables are keyed on **(`settlement_date` `YYYY-MM-DD`, `settlement_period` 1–48)** on the **UK-local clock** (Europe/London), identical to the `uk-system-price-forecast` repo so the two projects' CSVs join directly.

## Targets — imbalance price & NIV
| Field | Dataset | Endpoint | Notes |
|---|---|---|---|
| `ssp` → `imbalance_price` | System Prices | `GET /balancing/settlement/system-prices/{date}` | Single imbalance price since P305 (Nov 2018); `systemSellPrice`==`systemBuyPrice`. **Reused** from the forecast repo's `fetch_elexon.py`. |
| `net_imbalance_volume` (NIV) | System Prices | same | Sign = system long(+)/short(−). |

## Physical drivers — new fetchers in this repo
| Series | Dataset | Endpoint | Script | Hypothesis |
|---|---|---|---|---|
| `indo_mw`, `itsdo_mw` | **INDO / ITSDO** (Initial National / Transmission System Demand Outturn) | `GET /demand/outturn?settlementDateFrom=&settlementDateTo=` | `src/data/fetch_demand.py` | H1 net-demand ramp |
| `wind_mw`, `ccgt_mw`, `nuclear_mw`, … | **FUELHH** (generation by fuel type, MW) | `GET /datasets/FUELHH?settlementDateFrom=&settlementDateTo=` | `src/data/fetch_fuelhh.py` | H3 wind, H4 thermal margin |
| `interconnector_net_mw` | **FUELHH** (all `INT*` fuel codes summed) | same | `src/data/fetch_fuelhh.py` | H5 import tightening |

Base URL: `https://data.elexon.co.uk/bmrs/api/v1`. **No auth required** for Insights; if you have an Elexon key, set `ELEXON_API_KEY` and it is sent as `?apikey=…` for higher rate limits.

> **Confirm-on-first-run:** the demand and FUELHH parsers map the documented camelCase field names but keep a tolerant fallback — run each fetcher once against the live API and check the resulting columns, as Insights field names occasionally differ by deployment. The sandbox used to build this repo cannot reach `data.elexon.co.uk`, so the fetchers were verified against synthetic payloads, not live calls.

## Weather
| Field | Source | Notes |
|---|---|---|
| `temp_c`, `wind_ms`, `solar_wm2`, `precip_mm` | **Open-Meteo ERA5 archive** (free, no key) | Population-weighted England/Scotland/Wales. **Reused** from the forecast repo's `fetch_weather.py`. ~2-day archive lag. |

## Solar (gap to close next)
FUELHH covers only **transmission-metered** generation, so **embedded solar and embedded wind are excluded**. For absolute solar MW use **Sheffield Solar PV_Live** (`https://api.solar.sheffield.ac.uk/pvlive/api/v4`, free) or the **NESO Embedded Solar/Wind forecast**. Until then, `solar_wm2` irradiance from Open-Meteo is a usable proxy for the solar drop-off (H2).

## What is reused vs new
- **Reused from `uk-system-price-forecast`:** `system_prices_5yr.csv`, `weather_uk.csv`, `generation_mix.csv` (wind %/gas %), the SP/UK-time convention, and the retry/backoff + append/CLI fetcher pattern.
- **New here:** `fetch_demand.py`, `fetch_fuelhh.py` (absolute MW for demand, generation-by-fuel, interconnectors), the heatwave classification, and the diurnal analysis.
