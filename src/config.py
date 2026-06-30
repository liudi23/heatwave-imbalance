"""
Shared paths / config for the heatwave-Imbalance project.

Compatibility with the sister project `uk-system-price-forecast`:
this project deliberately reuses that repo's raw data (system prices, NIV,
weather, generation mix) rather than re-fetching it, and adds new physical
driver datasets (demand, generation-by-fuel, interconnectors) on top.

The location of the forecast repo is resolved in this order:
  1. env var  UK_FORECAST_REPO   (absolute path to the repo root)
  2. a sibling directory          ../uk-system-price-forecast
  3. this repo's own data/ folder  (once datasets have been copied in)

Schema is kept identical to the forecast repo: every half-hourly table is
keyed on (settlement_date [YYYY-MM-DD str], settlement_period [int 1..48])
on the UK-local clock, so tables from either project join directly.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"
FIGURES = REPO_ROOT / "figures"


def forecast_repo() -> Path:
    """Best-effort resolution of the sister uk-system-price-forecast repo."""
    env = os.environ.get("UK_FORECAST_REPO")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(REPO_ROOT.parent / "uk-system-price-forecast")
    for c in candidates:
        if (c / "data" / "raw").is_dir():
            return c
    # Fall back to this repo (datasets must have been copied locally).
    return REPO_ROOT


def forecast_raw() -> Path:
    return forecast_repo() / "data" / "raw"
