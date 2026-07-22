"""Open-Meteo daily UV-index source.

User-approved 2026-07-19 as the UV data source, with the Thailand-first policy
exception acknowledged explicitly: Open-Meteo is a non-Thai free service, but
it is queried at Nong Fab's own real Thailand coordinates (see
`nongfab_features.clearsky.nong_fab_site_location`), not a generic/global
default pointing elsewhere. It replaces NASA POWER for UV, whose real endpoint
has never been reachable from this deployment (see
`ingestion_scheduler._backfill_uv`'s own note) - so the dashboard's UV cell and
UV chart, which are already fully wired, simply had no data to show.

Free, no API key, daily `uv_index_max`. Daily resolution is exactly what the
dashboard's UV readouts already expect (see routes_weather / ForecastPage -
"UV เป็นรายวัน"), so no per-hour plumbing is needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_type

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE_NAME = "open-meteo"
# Open-Meteo caps historical `past_days` at 92; today + the forecast day are
# added on top via forecast_days=1.
MAX_PAST_DAYS = 92


@dataclass(frozen=True)
class UVObservation:
    """Matches what `RealDataStore.insert_uv_observations` reads off each item
    (observation_date / uv_index / source) - deliberately the same shape as
    `nasa_power_ingestion`'s own observation so the store insert is unchanged."""

    observation_date: date_type
    uv_index: float
    source: str = SOURCE_NAME


async def fetch_uv_observations(
    client: httpx.AsyncClient, latitude: float, longitude: float, past_days: int = MAX_PAST_DAYS
) -> list[UVObservation]:
    """Daily max UV index at (latitude, longitude) for the last `past_days`
    days plus today and the next forecast day. Returns oldest-first; skips any
    day Open-Meteo reports a null UV for (never fabricates a value). Raises on
    an HTTP/transport error - the caller wraps it so one failed refresh never
    crashes ingestion (same non-fatal contract as every other source)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "uv_index_max",
        "timezone": "Asia/Bangkok",
        "past_days": max(0, min(past_days, MAX_PAST_DAYS)),
        "forecast_days": 1,
    }
    resp = await client.get(OPEN_METEO_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    times = daily.get("time", []) or []
    uvs = daily.get("uv_index_max", []) or []
    observations: list[UVObservation] = []
    for iso_day, uv in zip(times, uvs):
        if uv is None:
            continue
        observations.append(UVObservation(observation_date=date_type.fromisoformat(iso_day), uv_index=float(uv)))
    return observations
