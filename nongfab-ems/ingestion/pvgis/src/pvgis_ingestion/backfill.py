"""Historical backfill: a single fetch_year() call, not a loop - PVGIS's
seriescalc API returns a whole year of already-published hourly data in one
request, unlike nwp/himawari's many small per-cycle fetches. Kept as its own
module for interface symmetry with the other ingestion modules' backfill.py
(same "seeds cold-start history" role), not because the mechanics need it.

IMPORTANT SCOPE NOTE (see schemas.py's PVGISHourlyPoint docstring for the full
reasoning): every point this produces has issue_time == valid_time, since PVGIS
is historical reanalysis, not a multi-lead-time forecast. Callers that write
these into forecast/local_store.py's shared nwp_history table get real weather
that genuinely helps Day-ahead training (real_data.real_day_frame/
real_future_regressors don't care about lead time) but is invisible to
Intra-day's k-step hour-ahead training (real_data.real_hour_frame_kstep filters
on lead_hours == 1..6, which these rows never match) - a deliberate 2026-07-16
decision, not an oversight to fix later.
"""

from __future__ import annotations

import logging

import httpx

from .config import Settings
from .datasource import DataUnavailableError, PVGISDataSource
from .schemas import PVGISHourlyPoint, RawFetchResult

logger = logging.getLogger(__name__)


async def backfill_year(
    settings: Settings,
    client: httpx.AsyncClient,
    year: int | None = None,
    target_latitude: float | None = None,
    target_longitude: float | None = None,
) -> tuple[RawFetchResult, list[PVGISHourlyPoint]] | None:
    """Fetches `year` (defaults to settings.year). Returns None (logged, not
    raised) if the year comes back empty, mirroring the per-source failure
    isolation of the other ingestion modules' backfill_range()/backfill_year() -
    PVGIS being unreachable shouldn't abort ingestion of NWP/cloud/UV data.
    """
    resolved_year = year if year is not None else settings.year
    source = PVGISDataSource(settings, client, target_latitude, target_longitude)
    logger.info("pvgis backfill: requesting year=%d", resolved_year)

    try:
        return await source.fetch_year(resolved_year)
    except DataUnavailableError:
        logger.warning("pvgis backfill: no usable data for year=%d", resolved_year, exc_info=True)
        return None
