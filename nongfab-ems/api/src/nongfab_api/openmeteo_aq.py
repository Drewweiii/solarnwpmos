"""Open-Meteo Air-Quality source: hourly aerosol / particulate drivers.

Added 2026-07-24 (user-approved external ingestion) to give the coastal PV
forecast the atmospheric-aerosol signals the literature shows improve accuracy
at sites affected by haze, dust and pollution (CAMS-AOD forcing studies reduce
overcast-day RMSE by up to ~25%). Open-Meteo's Air-Quality API is **powered by
CAMS** (the ECMWF Copernicus Atmosphere Monitoring Service global model), free
and key-less. Same Thailand-first exception already accepted for the UV source
(see openmeteo_uv.py): a non-Thai free service, but queried at Nong Fab's own
real Thailand coordinates, not a generic global default.

The four variables fetched, all hourly and forecast-capable (so a *future*
valid_time has an aerosol value, matching how the hour-ahead model joins them):
- `aerosol_optical_depth` -> aod_550nm (total column aerosol extinction)
- `dust`   -> near-surface mineral-dust concentration (ug/m3)
- `pm2_5`  -> fine particulate (ug/m3), a soiling + irradiance driver
- `pm10`   -> coarse particulate (ug/m3)

The marine SALT-spray driver is handled separately and needs no external
source: it is derived from wind + humidity in `nongfab_features.soiling`
(salt_soiling_index). Open-Meteo AQ does not expose a sea-salt-specific AOD, so
this module never fabricates one - it stores only what CAMS actually returns.

Like the CDN-loaded model in the 3D view, this source can't be exercised from
the egress-blocked dev sandbox; it comes alive on a real deploy. The parser is
unit-tested against a captured response shape so the wiring is verified offline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
SOURCE_NAME = "open-meteo-aq"
# Open-Meteo Air-Quality caps `past_days` at 92.
MAX_PAST_DAYS = 92
# ...and `forecast_days` at 7. Two is the default here (2026-07-25 fix): the
# hour-ahead model joins aerosol at each *future* valid_time up to +6h, and
# `forecast_days=1` means "today only" in UTC - so from ~18:00 UTC (01:00 ICT)
# onward the +1h..+6h leads ran off the end of the response and silently fell
# back to the neutral aerosol defaults. Asking for tomorrow too keeps at least
# 24h of forward coverage at every hour of the day.
MAX_FORECAST_DAYS = 7
DEFAULT_FORECAST_DAYS = 2
# The hourly variables requested, in the API's own naming.
HOURLY_VARS = ("aerosol_optical_depth", "dust", "pm2_5", "pm10")


@dataclass(frozen=True)
class AerosolPoint:
    """Matches what `RealDataStore.insert_aerosol_points` reads off each item
    (valid_time + aod_550nm/dust/pm2_5/pm10, any of which may be None + source).
    `valid_time` is a tz-aware UTC datetime, same convention as the NWP/cloud
    history so the hour-ahead join lines up."""

    valid_time: datetime
    aod_550nm: float | None
    dust: float | None
    pm2_5: float | None
    pm10: float | None
    source: str = SOURCE_NAME


def _opt_float(value: object) -> float | None:
    """Open-Meteo emits null for hours it has no value - keep those None (never
    fabricate a zero); coerce everything else to float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_aerosol_response(payload: dict) -> list[AerosolPoint]:
    """Turn an Open-Meteo Air-Quality JSON body into oldest-first AerosolPoints.
    Pure (no network) so it's unit-testable against a captured response. A row
    whose every aerosol field is null is skipped (nothing to store); partial
    rows are kept with None in the missing fields."""
    hourly = payload.get("hourly", {}) or {}
    times = hourly.get("time", []) or []
    aod = hourly.get("aerosol_optical_depth", []) or []
    dust = hourly.get("dust", []) or []
    pm2_5 = hourly.get("pm2_5", []) or []
    pm10 = hourly.get("pm10", []) or []
    points: list[AerosolPoint] = []
    for i, iso_hour in enumerate(times):
        a = _opt_float(aod[i]) if i < len(aod) else None
        d = _opt_float(dust[i]) if i < len(dust) else None
        p25 = _opt_float(pm2_5[i]) if i < len(pm2_5) else None
        p10 = _opt_float(pm10[i]) if i < len(pm10) else None
        if a is None and d is None and p25 is None and p10 is None:
            continue
        observed = datetime.fromisoformat(iso_hour).replace(tzinfo=timezone.utc)
        points.append(AerosolPoint(valid_time=observed, aod_550nm=a, dust=d, pm2_5=p25, pm10=p10))
    return points


async def fetch_aerosol_points(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    past_days: int = MAX_PAST_DAYS,
    forecast_days: int = DEFAULT_FORECAST_DAYS,
) -> list[AerosolPoint]:
    """Hourly aerosol/particulate at (latitude, longitude) for the last
    `past_days` days plus `forecast_days` days forward (today included).
    Timestamps requested in UTC and returned tz-aware UTC. Raises on HTTP/
    transport error - the caller wraps it so one failed refresh never crashes
    ingestion (same non-fatal contract as every other source)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
        "past_days": max(0, min(past_days, MAX_PAST_DAYS)),
        "forecast_days": max(1, min(forecast_days, MAX_FORECAST_DAYS)),
    }
    resp = await client.get(OPEN_METEO_AQ_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    return parse_aerosol_response(resp.json())
