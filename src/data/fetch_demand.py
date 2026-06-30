"""
Fetch GB electricity demand outturn (MW) from the Elexon Insights Solution API.

Datasets (BMRS / Insights):
    INDO   — Initial National Demand Outturn        (national demand, MW)
    ITSDO  — Initial Transmission System Demand Outturn (transmission demand, MW)

Endpoint:
    GET {BASE}/demand/outturn?settlementDateFrom=YYYY-MM-DD&settlementDateTo=YYYY-MM-DD
    (no auth required; an Elexon API key may be supplied via ELEXON_API_KEY
     and is sent as ?apikey=... if present, for higher rate limits.)

Output: data/raw/demand_outturn.csv
Cols:   settlement_date, settlement_period, indo_mw, itsdo_mw

Why this matters for the project:
    INDO/ITSDO are the demand side of *net demand* (demand - wind - solar),
    whose steep evening ramp (SP30 -> SP37) is hypothesis H1 for the 18:00 spike.

NOTE: field names returned by Insights can vary by deployment; the parser maps
the known camelCase names and otherwise keeps any *demand* numeric field. Run
once against the live API and confirm the columns on first use.

Usage:
    python src/data/fetch_demand.py                          # last 30 days
    python src/data/fetch_demand.py --start 2022-06-01 --end 2022-08-31
    python src/data/fetch_demand.py --start 2024-01-01 --append
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from _http import request_with_retry, parse_records  # noqa: E402  (run as script)

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
ENDPOINT = "/demand/outturn"
RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUTPUT_FILE = RAW_DATA_DIR / "demand_outturn.csv"
CHUNK_DAYS = 14

COLUMN_MAP = {
    "settlementDate": "settlement_date",
    "settlementPeriod": "settlement_period",
    "initialDemandOutturn": "indo_mw",
    "demand": "indo_mw",
    "initialTransmissionDemandOutturn": "itsdo_mw",
    "transmissionSystemDemand": "itsdo_mw",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _params(start: date, end: date) -> dict:
    p = {
        "settlementDateFrom": start.isoformat(),
        "settlementDateTo": end.isoformat(),
        "format": "json",
    }
    key = os.environ.get("ELEXON_API_KEY")
    if key:
        p["apikey"] = key
    return p


def fetch_chunk(start: date, end: date, session: requests.Session) -> pd.DataFrame:
    url = f"{BASE_URL}{ENDPOINT}"
    resp = request_with_retry(url, params=_params(start, end), session=session)
    records = parse_records(resp.json())
    if not records:
        log.warning("No records for %s -> %s", start, end)
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
    keep = [c for c in ("settlement_date", "settlement_period", "indo_mw", "itsdo_mw")
            if c in df.columns]
    df = df[keep].copy()
    if "settlement_date" in df.columns:
        df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.strftime("%Y-%m-%d")
    return df


def fetch_range(start: date, end: date, delay: float = 0.3) -> pd.DataFrame:
    session = requests.Session()
    frames: list[pd.DataFrame] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS - 1), end)
        log.info("Fetching demand %s -> %s", current, chunk_end)
        try:
            df = fetch_chunk(current, chunk_end, session)
            if not df.empty:
                frames.append(df)
        except requests.HTTPError as exc:
            log.error("HTTP %s for %s -> %s — skipping",
                      exc.response.status_code, current, chunk_end)
        except Exception as exc:  # noqa: BLE001
            log.error("Error %s -> %s: %s — skipping", current, chunk_end, exc)
        current = chunk_end + timedelta(days=1)
        time.sleep(delay)

    if not frames:
        return pd.DataFrame(columns=["settlement_date", "settlement_period",
                                     "indo_mw", "itsdo_mw"])
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
    parser = argparse.ArgumentParser(description="Fetch GB demand outturn (INDO/ITSDO, MW)")
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

    log.info("Fetching demand outturn %s -> %s", start, end)
    df = fetch_range(start, end)
    save(df, path, append=args.append)


if __name__ == "__main__":
    main()
