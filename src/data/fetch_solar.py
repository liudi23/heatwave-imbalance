"""
Fetch GB national embedded solar generation (MW) from Sheffield Solar PV_Live.

Why: FUELHH (fetch_fuelhh.py) covers only transmission-metered generation, so
distribution-connected ("embedded") solar — most of GB solar — is invisible to
it. PV_Live is the standard open estimate of national solar outturn, and gives
this project the absolute solar MW needed to build true net demand
(demand - wind - solar) and to quantify the evening solar drop-off (H2).

API:    https://api.solar.sheffield.ac.uk/pvlive/api/v4   (free, no key)
        GSP id 0 = GB national.
Output: data/raw/solar_pvlive.csv
Cols:   settlement_date, settlement_period, solar_mw

TIME ALIGNMENT: PV_Live `datetime_gmt` is the PERIOD-ENDING timestamp in UTC.
We shift back 30 min to the period *start*, convert to Europe/London, and derive
SP = hour*2 + minute//30 + 1 — the same UK-local convention as every other table
in this project. (Confirm the period-ending assumption on first live run; flip
PERIOD_ENDING = False if PV_Live is treated as period-starting.)

Usage:
    python src/data/fetch_solar.py                          # last 30 days
    python src/data/fetch_solar.py --start 2022-06-01 --end 2022-08-31
    python src/data/fetch_solar.py --start 2024-01-01 --append
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from _http import request_with_retry  # noqa: E402  (run as script)

BASE_URL = "https://api.solar.sheffield.ac.uk/pvlive/api/v4"
GSP_ID = 0                      # national
RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUTPUT_FILE = RAW_DATA_DIR / "solar_pvlive.csv"
CHUNK_DAYS = 30
PERIOD_ENDING = True           # PV_Live timestamps are period-ending

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _parse(payload: dict) -> pd.DataFrame:
    """PV_Live {meta:[cols], data:[[...]]} -> SP-indexed solar_mw table."""
    meta = payload.get("meta") or []
    data = payload.get("data") or []
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=meta) if meta else pd.DataFrame(data)
    # Be tolerant about column naming across API versions.
    tcol = next((c for c in df.columns if str(c).lower().startswith("datetime")), None)
    gcol = next((c for c in df.columns if "generation" in str(c).lower()), None)
    if tcol is None or gcol is None:
        log.warning("Unexpected PV_Live shape; columns=%s", list(df.columns))
        return pd.DataFrame()

    ts = pd.to_datetime(df[tcol], utc=True)
    if PERIOD_ENDING:
        ts = ts - pd.Timedelta(minutes=30)          # -> period start
    uk = ts.dt.tz_convert("Europe/London")
    out = pd.DataFrame({
        "settlement_date": uk.dt.strftime("%Y-%m-%d"),
        "settlement_period": uk.dt.hour * 2 + uk.dt.minute // 30 + 1,
        "solar_mw": pd.to_numeric(df[gcol], errors="coerce"),
    })
    return out.dropna(subset=["solar_mw"])


def fetch_chunk(start: date, end: date, session: requests.Session) -> pd.DataFrame:
    # end-of-day inclusive: query to 23:30 period-ending of the end date
    params = {
        "start": f"{start.isoformat()}T00:00:00",
        "end": f"{end.isoformat()}T23:59:59",
    }
    url = f"{BASE_URL}/gsp/{GSP_ID}"
    resp = request_with_retry(url, params=params, session=session)
    return _parse(resp.json())


def fetch_range(start: date, end: date, delay: float = 0.3) -> pd.DataFrame:
    session = requests.Session()
    frames: list[pd.DataFrame] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS - 1), end)
        log.info("Fetching solar %s -> %s", current, chunk_end)
        try:
            df = fetch_chunk(current, chunk_end, session)
            if not df.empty:
                df = df[(df["settlement_date"] >= str(current)) &
                        (df["settlement_date"] <= str(chunk_end))]
                frames.append(df)
        except requests.HTTPError as exc:
            log.error("HTTP %s for %s -> %s — skipping",
                      exc.response.status_code, current, chunk_end)
        except Exception as exc:  # noqa: BLE001
            log.error("Error %s -> %s: %s — skipping", current, chunk_end, exc)
        current = chunk_end + timedelta(days=1)
        time.sleep(delay)

    if not frames:
        return pd.DataFrame(columns=["settlement_date", "settlement_period", "solar_mw"])
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["settlement_date", "settlement_period"])
        .sort_values(["settlement_date", "settlement_period"])
        .reset_index(drop=True)
    )


def save(df: pd.DataFrame, path: Path, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if append and path.exists():
        existing = pd.read_csv(path)
        existing["settlement_date"] = existing["settlement_date"].astype(str)
        df = (
            pd.concat([existing, df], ignore_index=True)
            .drop_duplicates(subset=["settlement_date", "settlement_period"])
            .sort_values(["settlement_date", "settlement_period"])
        )
    df.to_csv(path, index=False)
    log.info("Saved %d rows -> %s", len(df), path)


def _last_date(path: Path) -> Optional[date]:
    if not path.exists():
        return None
    df = pd.read_csv(path, usecols=["settlement_date"])
    return date.fromisoformat(str(df["settlement_date"].max())) if not df.empty else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GB national embedded solar (PV_Live, MW)")
    default_end = date.today() - timedelta(days=1)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=str(default_end))
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()

    path = Path(args.output)
    end = date.fromisoformat(args.end)
    if args.start is None:
        last = _last_date(path)
        start = (last + timedelta(days=1)) if last else (end - timedelta(days=29))
        if last:
            args.append = True
    else:
        start = date.fromisoformat(args.start)

    if start > end:
        log.info("Already up to date (last=%s). Nothing to fetch.", start - timedelta(days=1))
        return

    log.info("Fetching PV_Live solar %s -> %s", start, end)
    df = fetch_range(start, end)
    save(df, path, append=args.append)


if __name__ == "__main__":
    main()
