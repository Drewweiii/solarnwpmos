"""PVGIS seriescalc adapter - fetches one full year of real hourly ERA5-reanalysis
weather (irradiance G(i), 2m temperature T2m, 10m wind speed WS10m) for Nong Fab's
own coordinates, in a single HTTP call (unlike nwp/himawari's many small per-cycle
fetches). See schemas.py's PVGISHourlyPoint docstring for why every row's
issue_time == valid_time, and this module's README for the "Day-ahead only, not
Intra-day" scope decision that follows from that.

Live-verified 2026-07-16: this dev sandbox's own egress policy returns a hard 403
for re.jrc.ec.europa.eu (same blanket block as every other external host tried -
see README "Data source & ToS"), but the user confirmed a real HTTP 200 with real
Nong-Fab-coordinate data via a one-off script run in the Railway deployment's own
console - this module is built against that genuine captured response shape
(fixtures/sample_seriescalc_response.json), not guessed from documentation alone
(unlike nasa_power_ingestion, which never got a live sample at all).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Settings
from .schemas import SOURCE_NAME, PVGISHourlyPoint, RawFetchResult

# PVGIS provides no relative humidity field - forecast/local_store.py's shared
# nwp_history table schema requires a value in every row regardless of source
# (see PVGISHourlyPoint's own docstring on why this is an unused placeholder, not
# a real reading). A mid-range value keeps it inside the table's own documented
# valid range (0-105) without implying false precision.
_UNAVAILABLE_RH_PLACEHOLDER_PCT = 70.0


class PVGISSource(ABC):
    """Adapter interface so the ingestion pipeline can swap in a different
    reanalysis/climatology provider later without touching backfill.py - mirrors
    nasa_power_ingestion.datasource.UVDataSource's own pattern.
    """

    @abstractmethod
    async def fetch_year(self, year: int) -> tuple[RawFetchResult, list[PVGISHourlyPoint]]:
        """One full year of hourly points - seriescalc is inherently year-scoped
        (no day-level slicing), unlike nasa_power's arbitrary date-range API.
        """


class DataUnavailableError(RuntimeError):
    """PVGIS returned no usable hourly rows for the requested year."""


def _parse_seriescalc_response(body: bytes, latitude: float, longitude: float, source_label: str) -> list[PVGISHourlyPoint]:
    """Parses PVGIS's documented seriescalc JSON response shape:
    {"inputs": {...}, "outputs": {"hourly": [{"time": "YYYYMMDD:HHMM", "G(i)":
    <W/m2>, "T2m": <degC>, "WS10m": <m/s>, ...}, ...]}, "meta": {...}}
    `time` is UTC (PVGIS's own convention, not locale-dependent) at :30 past each
    hour - the offset is PVGIS's own hourly-midpoint labeling, not rounded here
    (this module's rows aren't required to land on clean :00 boundaries the way
    serving.py's forecast timestamps are - see that module's `_ceil_to`, a
    different concern entirely: display-time anchoring, not historical backfill).
    """
    payload = json.loads(body)
    hourly_rows: list[dict] = payload["outputs"]["hourly"]

    points = []
    for row in hourly_rows:
        valid_time = datetime.strptime(row["time"], "%Y%m%d:%H%M").replace(tzinfo=timezone.utc)
        points.append(
            PVGISHourlyPoint(
                valid_time=valid_time,
                issue_time=valid_time,  # historical reanalysis, not a forecast - see schemas.py
                latitude=latitude,
                longitude=longitude,
                ssrd_w_m2=row["G(i)"],
                temp2m_c=row["T2m"],
                wind10m_u_ms=row.get("WS10m", 0.0),  # real speed, no direction available - see schemas.py
                wind10m_v_ms=0.0,
                relative_humidity_pct=_UNAVAILABLE_RH_PLACEHOLDER_PCT,
                source=source_label,
            )
        )
    return points


class PVGISDataSource(PVGISSource):
    """Real adapter: PVGIS (Photovoltaic Geographical Information System),
    European Commission Joint Research Centre - public, free, no API key/
    registration required (see README "Data source & ToS").
    """

    SOURCE_NAME = SOURCE_NAME

    def __init__(self, settings: Settings, client: httpx.AsyncClient, target_latitude: float | None = None, target_longitude: float | None = None):
        self._settings = settings
        self._client = client
        self._target_lat = target_latitude if target_latitude is not None else settings.site_latitude
        self._target_lon = target_longitude if target_longitude is not None else settings.site_longitude

    async def fetch_year(self, year: int) -> tuple[RawFetchResult, list[PVGISHourlyPoint]]:
        settings = self._settings
        params = {
            "lat": str(self._target_lat),
            "lon": str(self._target_lon),
            "startyear": str(year),
            "endyear": str(year),
            "pvcalculation": "1",
            "peakpower": str(settings.reference_peak_power_kwp),
            "loss": str(settings.system_loss_pct),
            "outputformat": "json",
        }

        @retry(
            stop=stop_after_attempt(settings.max_retry_attempts),
            wait=wait_exponential(multiplier=settings.retry_backoff_base_seconds, max=settings.retry_backoff_max_seconds),
            reraise=True,
        )
        async def _do_fetch() -> httpx.Response:
            resp = await self._client.get(
                settings.base_url, params=params, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent}
            )
            resp.raise_for_status()
            return resp

        resp = await _do_fetch()
        raw = RawFetchResult(url=str(resp.request.url), fetched_at=datetime.now(timezone.utc), content_type="application/json", body=resp.content)
        points = _parse_seriescalc_response(resp.content, self._target_lat, self._target_lon, self.SOURCE_NAME)
        if not points:
            raise DataUnavailableError(f"PVGIS returned no usable hourly rows for year={year}")
        return raw, points


class MockPVGISSource(PVGISSource):
    """Fixture-backed source for local dev and tests - the default
    (config.source_mode="mock"). The fixture's `outputs.hourly`/`inputs.location`/
    `inputs.meteo_data` are a genuine response captured live via the Railway
    deployment's own console (its egress can reach PVGIS; this dev sandbox's
    cannot - see README) - not invented from documentation alone. Only 3 hourly
    rows (not a full year) are kept, since this fixture exists to exercise the
    parsing/plumbing, not to seed a production-quality training corpus.
    """

    SOURCE_NAME = "mock-fixture"

    def __init__(self, settings: Settings, fixture_path: Path | None = None):
        self._settings = settings
        package_root = Path(__file__).resolve().parent.parent.parent
        self._fixture_path = fixture_path or (package_root / "fixtures" / "sample_seriescalc_response.json")

    async def fetch_year(self, year: int) -> tuple[RawFetchResult, list[PVGISHourlyPoint]]:
        body = Path(self._fixture_path).read_bytes()
        now = datetime.now(timezone.utc)
        raw = RawFetchResult(url="mock://pvgis-fixture", fetched_at=now, content_type="application/json", body=body)
        points = _parse_seriescalc_response(body, self._settings.site_latitude, self._settings.site_longitude, self.SOURCE_NAME)

        # Reindex the fixture's fixed 2020-01-01 dates onto the requested `year` so
        # callers see plausible dates for whatever year they asked for, same
        # "reindex, don't fabricate a full year" approach as nasa_power_ingestion's
        # MockUVDataSource.
        reindexed = [
            p.model_copy(update={"valid_time": p.valid_time.replace(year=year), "issue_time": p.issue_time.replace(year=year)})
            for p in points
        ]
        return raw, reindexed


def build_datasource(settings: Settings, client: httpx.AsyncClient | None = None) -> PVGISSource:
    if settings.source_mode == "mock":
        return MockPVGISSource(settings)

    if client is None:
        raise ValueError("http source mode requires an httpx client")
    return PVGISDataSource(settings, client)
