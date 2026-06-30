"""
Fetch GB half-hourly generation by fuel type (MW) incl. interconnectors —
Elexon Insights dataset FUELHH.

Dataset: FUELHH — half-hourly generation outturn by BM fuel type (MW).
Endpoint:
    GET {BASE}/datasets/FUELHH?settlementDateFrom=YYYY-MM-DD&settlementDateTo=YYYY-MM-DD
    (no auth required; ELEXON_API_KEY sent as ?apikey=... if present.)

The dataset is "long" (one row per fuel type per settlement period). We pivot
it wide and derive the series this project needs:
    wind_mw            — transmission-metered wind (NB: embedded wind/solar are
                         NOT in FUELHH; solar is added separately via PV_Live)
    ccgt_mw, nuclear_mw, coal_mw, biomass_mw   — key thermal stack
    interconnector_net_mw  — sum of all INT* fuel types (>0 = net import)
    total_generation_mw    — sum of all fuel types

Output: data/raw/generation_fuelhh.csv
Cols:   settlement_date, settlement_period, <fuel>_mw ..., interconnector_net_mw

Project relevance:
    wind_mw  -> hypothesis H3 (low wind under anticyclonic heat)
    ccgt/nuclear margin -> H4 (thermal derating)
    interconnector_net_mw -> H5 (import tightening when neighbours are hot too)

FUEL TYPE NOTES: keys are upper-case BMRS codes (CCGT, OCGT, OIL, COAL,
NUCLEAR, WIND, PS, NPSHYD, BIOMASS, OTHER, and interconnectors INTFR, INTIRL,
INTNED, INTEW, INTNEM, INTELEC, INTIFA2, INTNSL, INTVKL, INTGRNL, ...). The
INT* set grows as new links open; we match the prefix rather than a fixed list.

Usage:
    python src/data/fetch_fuelhh.py                          # last 30 days
    python src/data/fetch_fuelhh.py --start 2022-06-01 --end 2022-08-31
    python src/data/fetch_fuelhh.py --start 2024-01-01 --append
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

from _http import request_with_retry, parse_records  # noqa: E402

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
ENDPOINT = "/datasets/FUELHH"
RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUTPUT_FILE = RAW_DATA_DIR / "generation_fuelhh.csv"
CHUNK_DAYS = 7

# Named thermal/renewable fuels we surface explicitly; everything else is still
# summed into total_generation_mw and (for INT*) interconnector_net_mw.
NAMED_FUELS = ["CCGT", "OCGT", "OIL", "COAL", "NUCLEAR", "WIND", "PS",
               "NPSHYD", "BIOMASS", "OTHER"]

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


def _pivot(records: list) -> pd.DataFrame:
    """Long FUELHH records -> wide MW table keyed on (date, period)."""
    df = pd.DataFrame(records)
    # Tolerate camelCase field naming differences.
    ren = {
        "settlementDate": "settlement_date",
        "settlementPeriod": "settlement_period",
        "fuelType": "fuel_type",
        "generation": "mw",
        "quantity": "mw",
    }
    df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})
    need = {"settlement_date", "settlement_period", "fuel_type", "mw"}
    if not need.issubset(df.columns):
        log.warning("Unexpected FUELHH shape; columns=%s", list(df.columns))
        return pd.DataFrame()

    df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.strftime("%Y-%m-%d")
    df["fuel_type"] = df["fuel_type"].str.upper()
    df["mw"] = pd.to_numeric(df["mw"], errors="coerce")

    wide = (
        df.pivot_table(index=["settlement_date", "settlement_period"],
                       columns="fuel_type", values="mw", aggfunc="sum")
        .reset_index()
    )
    wide.columns.name = None

    fuels = [c for c in wide.columns if c not in ("settlement_date", "settlement_period")]
    int_cols = [c for c in fuels if c.startswith("INT")]
    wide["interconnector_net_mw"] = wide[int_cols].sum(axis=1) if int_cols else 0.0
    wide["total_generation_mw"] = wide[fuels].sum(axis=1)

    out = wide[["settlement_date", "settlement_period"]].copy()
    for f in NAMED_FUELS:
        if f in wide.columns:
            out[f"{f.lower()}_mw"] = wide[f]
    out["interconnector_net_mw"] = wide["interconnector_net_mw"]
    out["total_generation_mw"] = wide["total_generation_mw"]
    return out


def fetch_chunk(start: date, end: date, session: requests.Session) -> pd.DataFrame:
    url = f"{BASE_URL}{ENDPOINT}"
    resp = request_with_retry(url, params=_params(start, end), session=session)
    records = parse_records(resp.json())
    if not records:
        log.warning("No FUELHH records for %s -> %s", start, end)
        return pd.DataFrame()
    return _pivot(records)


def fetch_range(start: date, end: date, delay: float = 0.3) -> pd.DataFrame:
    session = requests.Session()
    frames: list[pd.DataFrame] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS - 1), end)
        log.info("Fetching FUELHH %s -> %s", current, chunk_end)
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
        return pd.DataFrame()
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
    parser = argparse.ArgumentParser(description="Fetch GB generation by fuel (FUELHH, MW)")
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

    log.info("Fetching FUELHH %s -> %s", start, end)
    df = fetch_range(start, end)
    save(df, path, append=args.append)


if __name__ == "__main__":
    main()
