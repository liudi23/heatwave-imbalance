"""Shared HTTP helper — same retry/backoff contract as the sister forecast repo.

Kept in one place so every fetcher in this project behaves identically to
fetch_elexon.py / fetch_weather.py in uk-system-price-forecast.
"""
from __future__ import annotations

import logging
import time

import requests

TIMEOUT = 60
MAX_RETRIES = 3
BACKOFF_BASE = 5  # seconds; delays are 5, 10, 20

log = logging.getLogger(__name__)


def request_with_retry(url: str, params=None, session: requests.Session | None = None):
    """GET with exponential backoff. Raises the last exception on final failure."""
    getter = session.get if session is not None else requests.get
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(MAX_RETRIES):
        try:
            resp = getter(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except (requests.RequestException, OSError) as exc:
            last_exc = exc
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning("attempt %d/%d failed (%s: %s); retrying in %ds",
                        attempt + 1, MAX_RETRIES, type(exc).__name__, exc, wait)
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
    raise last_exc


def parse_records(payload) -> list:
    """Extract a list of records from the common Insights response shapes."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []
