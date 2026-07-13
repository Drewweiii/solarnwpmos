from __future__ import annotations

import json
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .compliance import RateLimiter, RobotsChecker
from .config import Settings
from .schemas import CloudObservation, RawFetchResult

logger = logging.getLogger(__name__)


class ComplianceError(RuntimeError):
    """Raised when a fetch is blocked by the robots.txt/ToS gate."""


class CloudDataSource(ABC):
    """Adapter interface so the ingestion pipeline can swap data providers later
    (e.g. an official paid API) without touching the scheduler or storage layer.
    """

    @abstractmethod
    async def fetch_latest(self) -> tuple[RawFetchResult, CloudObservation]:
        """Return the raw payload (for audit/replay storage) and the parsed, validated observation."""


def _parse_json_response(payload: dict, source_name: str) -> CloudObservation:
    """Maps the provider's JSON fields to our schema.

    NOTE: field names below (timestamp/latitude/longitude/cloud_opacity/cloud_index)
    are a placeholder mapping. himawari.optemis.space currently fails TLS validation
    (certificate expired, verified 2026-07-13) so the real response shape could not
    be inspected - recalibrate this function against a live response before relying
    on HimawariOptemisSource in production. See module README "Known limitation".
    """
    return CloudObservation(
        observed_at=datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00")),
        latitude=payload["latitude"],
        longitude=payload["longitude"],
        cloud_opacity_pct=payload["cloud_opacity"],
        cloud_index=payload["cloud_index"],
        source=source_name,
    )


class HimawariOptemisSource(CloudDataSource):
    """Real HTTP adapter for himawari.optemis.space. See _parse_json_response docstring
    for the current calibration caveat.
    """

    SOURCE_NAME = "himawari.optemis.space"

    def __init__(self, settings: Settings, client: httpx.AsyncClient, robots: RobotsChecker, rate_limiter: RateLimiter):
        self._settings = settings
        self._client = client
        self._robots = robots
        self._rate_limiter = rate_limiter

    async def fetch_latest(self) -> tuple[RawFetchResult, CloudObservation]:
        decision = await self._robots.is_allowed(self._settings.api_path, self._client)
        if not decision.allowed:
            raise ComplianceError(decision.reason)

        await self._rate_limiter.wait()
        raw = await self._get_with_retry()
        observation = _parse_json_response(json.loads(raw.body), self.SOURCE_NAME)
        return raw, observation

    async def _get_with_retry(self) -> RawFetchResult:
        settings = self._settings

        @retry(
            stop=stop_after_attempt(settings.max_retry_attempts),
            wait=wait_exponential(multiplier=settings.retry_backoff_base_seconds, max=settings.retry_backoff_max_seconds),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        )
        async def _do_request() -> RawFetchResult:
            url = self._settings.base_url + self._settings.api_path
            resp = await self._client.get(
                url,
                timeout=settings.request_timeout_seconds,
                headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
                params={"lat": settings.site_latitude, "lon": settings.site_longitude},
            )
            resp.raise_for_status()
            return RawFetchResult(
                url=url,
                fetched_at=datetime.now(timezone.utc),
                content_type=resp.headers.get("content-type", "application/octet-stream"),
                body=resp.content,
            )

        return await _do_request()


class MockCloudDataSource(CloudDataSource):
    """Fixture-backed source for local dev and tests - the default (config.source_mode="mock"),
    so the rest of the pipeline is fully exercisable without depending on the live site.
    """

    SOURCE_NAME = "mock-fixture"

    def __init__(self, settings: Settings, fixture_path: Path | None = None, jitter: bool = True):
        self._settings = settings
        # himawari/src/himawari_ingestion/datasource.py -> himawari/fixtures/...
        package_root = Path(__file__).resolve().parent.parent.parent
        self._fixture_path = fixture_path or (package_root / "fixtures" / "sample_himawari_response.json")
        self._jitter = jitter

    async def fetch_latest(self) -> tuple[RawFetchResult, CloudObservation]:
        payload = json.loads(Path(self._fixture_path).read_text())
        now = datetime.now(timezone.utc)
        payload["timestamp"] = now.isoformat()
        payload["latitude"] = self._settings.site_latitude
        payload["longitude"] = self._settings.site_longitude
        if self._jitter:
            payload["cloud_opacity"] = min(100, max(0, payload["cloud_opacity"] + random.uniform(-10, 10)))
            payload["cloud_index"] = min(1.5, max(-0.2, payload["cloud_index"] + random.uniform(-0.1, 0.1)))

        body = json.dumps(payload).encode("utf-8")
        raw = RawFetchResult(url="mock://himawari-fixture", fetched_at=now, content_type="application/json", body=body)
        observation = _parse_json_response(payload, self.SOURCE_NAME)
        return raw, observation


def build_datasource(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    robots: RobotsChecker | None = None,
    rate_limiter: RateLimiter | None = None,
) -> CloudDataSource:
    if settings.source_mode == "mock":
        return MockCloudDataSource(settings)

    if client is None or robots is None or rate_limiter is None:
        raise ValueError("http source mode requires an httpx client, RobotsChecker and RateLimiter")
    return HimawariOptemisSource(settings, client, robots, rate_limiter)
