from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .compliance import RateLimiter
from .config import Settings
from .schemas import RawFetchResult, UVObservation


class UVDataSource(ABC):
    """Adapter interface so the ingestion pipeline can swap UV providers later
    without touching the scheduler/storage layer - mirrors himawari_ingestion's
    CloudDataSource / nwp_ingestion's NWPDataSource pattern.
    """

    @abstractmethod
    async def fetch_range(self, start: date, end: date) -> tuple[RawFetchResult, list[UVObservation]]:
        """NASA POWER's daily point API is inherently range-based (one request
        returns every day in [start, end]) rather than "latest single value" - unlike
        Himawari/GFS's near-real-time cadence, so there's no separate fetch_latest()
        here; a 1-day range *is* "latest".
        """


class DataUnavailableError(RuntimeError):
    """NASA POWER returned no usable (non-missing-sentinel) values for the requested range."""


def _parse_power_response(body: bytes, parameter: str, latitude: float, longitude: float, source_label: str) -> list[UVObservation]:
    """Parses NASA POWER's documented JSON response shape:
    {"properties": {"parameter": {"<PARAM>": {"YYYYMMDD": <value>, ...}}}}
    Skips (does not raise on) individual missing-sentinel days - see README "Data
    source & ToS" for why a partial day gap shouldn't fail the whole fetch.
    """
    payload = json.loads(body)
    daily_values: dict[str, float] = payload["properties"]["parameter"][parameter]

    observations = []
    for date_str, value in daily_values.items():
        if value <= -900:  # NASA POWER's missing-data sentinel (~-999)
            continue
        observations.append(
            UVObservation(
                observation_date=datetime.strptime(date_str, "%Y%m%d").date(),
                latitude=latitude,
                longitude=longitude,
                uv_index=value,
                source=source_label,
            )
        )
    return sorted(observations, key=lambda o: o.observation_date)


class NASAPowerDataSource(UVDataSource):
    """Real adapter: NASA POWER (Prediction Of Worldwide Energy Resources) daily
    point API - public, free, no API key/registration required. See README "Data
    source & ToS" for the compliance review performed before this was written.

    NOT live-verified against the real endpoint from this dev sandbox - its egress
    policy returns a hard 403 for power.larc.nasa.gov (unlike the S3-hosted
    Himawari/GFS sources, which are reachable here). Built against NASA POWER's
    long-stable, publicly documented response shape instead - see README for the
    exact gap and how to close it (a quick live curl, either by a user with
    unrestricted egress or once this deploys to Railway).
    """

    SOURCE_NAME = "nasa-power-daily"

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient, rate_limiter: RateLimiter,
        target_latitude: float | None = None, target_longitude: float | None = None,
    ):
        self._settings = settings
        self._client = client
        self._rate_limiter = rate_limiter
        self._target_lat = target_latitude if target_latitude is not None else settings.site_latitude
        self._target_lon = target_longitude if target_longitude is not None else settings.site_longitude

    async def fetch_range(self, start: date, end: date) -> tuple[RawFetchResult, list[UVObservation]]:
        settings = self._settings
        params = {
            "parameters": settings.parameters,
            "community": settings.community,
            "longitude": str(self._target_lon),
            "latitude": str(self._target_lat),
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
        }

        @retry(
            stop=stop_after_attempt(settings.max_retry_attempts),
            wait=wait_exponential(multiplier=settings.retry_backoff_base_seconds, max=settings.retry_backoff_max_seconds),
            reraise=True,
        )
        async def _do_fetch() -> httpx.Response:
            await self._rate_limiter.wait()
            resp = await self._client.get(
                settings.base_url, params=params, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent}
            )
            resp.raise_for_status()
            return resp

        resp = await _do_fetch()
        raw = RawFetchResult(url=str(resp.request.url), fetched_at=datetime.now(timezone.utc), content_type="application/json", body=resp.content)
        observations = _parse_power_response(resp.content, settings.parameters, self._target_lat, self._target_lon, self.SOURCE_NAME)
        if not observations:
            raise DataUnavailableError(f"NASA POWER returned no usable {settings.parameters} values for [{start}, {end}]")
        return raw, observations


class MockUVDataSource(UVDataSource):
    """Fixture-backed source for local dev and tests - the default
    (config.source_mode="mock"). The fixture is constructed from NASA POWER's
    documented response shape (see fixtures/README note), not a captured live
    response - this module could not be live-verified from this dev sandbox
    (power.larc.nasa.gov is blocked by its egress policy). See module README.
    """

    SOURCE_NAME = "mock-fixture"

    def __init__(self, settings: Settings, fixture_path: Path | None = None):
        self._settings = settings
        package_root = Path(__file__).resolve().parent.parent.parent
        self._fixture_path = fixture_path or (package_root / "fixtures" / "sample_power_response.json")

    async def fetch_range(self, start: date, end: date) -> tuple[RawFetchResult, list[UVObservation]]:
        body = Path(self._fixture_path).read_bytes()
        now = datetime.now(timezone.utc)
        raw = RawFetchResult(url="mock://nasa-power-fixture", fetched_at=now, content_type="application/json", body=body)
        observations = _parse_power_response(
            body, self._settings.parameters, self._settings.site_latitude, self._settings.site_longitude, self.SOURCE_NAME
        )

        # Reindex the fixture's fixed calendar dates onto [start, end] so callers
        # (backfill.py in particular) see plausible dates for whatever range they
        # asked for, rather than always the fixture's own hardcoded dates.
        span_days = (end - start).days + 1
        reindexed = []
        for i in range(min(span_days, len(observations))):
            obs = observations[i % len(observations)]
            reindexed.append(obs.model_copy(update={"observation_date": start + timedelta(days=i)}))
        return raw, reindexed


def build_datasource(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    rate_limiter: RateLimiter | None = None,
) -> UVDataSource:
    if settings.source_mode == "mock":
        return MockUVDataSource(settings)

    if client is None or rate_limiter is None:
        raise ValueError("http source mode requires an httpx client and a RateLimiter")
    return NASAPowerDataSource(settings, client, rate_limiter)
