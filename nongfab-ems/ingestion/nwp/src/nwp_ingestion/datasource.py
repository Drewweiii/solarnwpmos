from __future__ import annotations

import asyncio
import logging
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from .compliance import RateLimiter
from .config import Settings
from .geolocation import FetchBBox, nong_fab_fetch_bbox
from .schemas import NWPForecastPoint, RawFetchResult

logger = logging.getLogger(__name__)

_KELVIN_TO_CELSIUS = 273.15


class NWPDataSource(ABC):
    """Adapter interface so the ingestion pipeline can swap NWP providers later
    without touching the scheduler or storage layer. Mirrors himawari_ingestion's
    CloudDataSource pattern.
    """

    @abstractmethod
    async def fetch_latest_cycle(self) -> list[tuple[RawFetchResult, NWPForecastPoint]]:
        """Returns one (raw GRIB2 payload, validated forecast point) pair per
        forecast hour of the most recently published GFS cycle.
        """


class DataUnavailableError(RuntimeError):
    """No published GFS cycle was found within the configured lookback window."""


def _build_filter_url(settings: Settings, cycle_issue_time: datetime, forecast_hour: int, bbox: FetchBBox) -> str:
    """Builds a NOMADS GFS filter/subset request URL - the officially documented way
    to fetch a small slice of a GRIB2 file rather than the full multi-GB file.
    Verified live 2026-07-14 against nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl.
    """
    dir_path = settings.nomads_prod_dir_template.format(date=cycle_issue_time, cycle=cycle_issue_time.hour)
    file_name = settings.gfs_file_template.format(cycle=cycle_issue_time.hour, fhour=forecast_hour)
    params = {
        "file": file_name,
        "dir": dir_path,
        "var_DSWRF": "on",
        "var_TMP": "on",
        "var_RH": "on",
        "var_UGRD": "on",
        "var_VGRD": "on",
        "lev_surface": "on",
        "lev_2_m_above_ground": "on",
        "lev_10_m_above_ground": "on",
        "subregion": "",
        "toplat": str(bbox.lat_max),
        "leftlon": str(bbox.lon_min),
        "rightlon": str(bbox.lon_max),
        "bottomlat": str(bbox.lat_min),
    }
    return f"{settings.nomads_base_url}?{urlencode(params)}"


def _decode_grib_sync(grib_bytes: bytes, target_lat: float, target_lon: float, source_label: str) -> NWPForecastPoint:
    """Blocking: decodes a small GRIB2 subset via cfgrib/xarray and samples the grid
    point nearest to Nong Fab. Must run off the event loop - see
    NomadsGfsDataSource._decode.

    Opens the file three times with distinct `filter_by_keys` (surface/sdswrf,
    heightAboveGround=2, heightAboveGround=10) rather than once - verified live that
    a single open_dataset() call raises cfgrib.dataset.DatasetBuildError when 2m and
    10m heightAboveGround fields are mixed (cfgrib can't merge two different fixed
    values of the same coordinate into one Dataset).
    """
    import xarray as xr

    with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
        tmp.write(grib_bytes)
        tmp.flush()

        ds_2m = xr.open_dataset(
            tmp.name, engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround", "level": 2}, "indexpath": ""},
        )
        ds_10m = xr.open_dataset(
            tmp.name, engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"typeOfLevel": "heightAboveGround", "level": 10}, "indexpath": ""},
        )
        ds_sfc = xr.open_dataset(
            tmp.name, engine="cfgrib",
            backend_kwargs={"filter_by_keys": {"typeOfLevel": "surface", "shortName": "sdswrf"}, "indexpath": ""},
        )

        t2m = ds_2m["t2m"].sel(latitude=target_lat, longitude=target_lon, method="nearest")
        r2 = ds_2m["r2"].sel(latitude=target_lat, longitude=target_lon, method="nearest")
        u10 = ds_10m["u10"].sel(latitude=target_lat, longitude=target_lon, method="nearest")
        v10 = ds_10m["v10"].sel(latitude=target_lat, longitude=target_lon, method="nearest")
        sdswrf = ds_sfc["sdswrf"].sel(latitude=target_lat, longitude=target_lon, method="nearest")

        matched_lat = float(t2m["latitude"].item())
        matched_lon = float(t2m["longitude"].item())
        issue_time = pd.Timestamp(ds_2m["time"].values).to_pydatetime().replace(tzinfo=timezone.utc)
        valid_time = pd.Timestamp(ds_2m["valid_time"].values).to_pydatetime().replace(tzinfo=timezone.utc)

        return NWPForecastPoint(
            issue_time=issue_time,
            valid_time=valid_time,
            latitude=matched_lat,
            longitude=matched_lon,
            ssrd_w_m2=float(sdswrf.item()),
            temp2m_c=float(t2m.item()) - _KELVIN_TO_CELSIUS,
            wind10m_u_ms=float(u10.item()),
            wind10m_v_ms=float(v10.item()),
            relative_humidity_pct=float(r2.item()),
            source=source_label,
        )


def _most_recent_published_cycle(now: datetime, cycles: list[int], publish_latency_minutes: int) -> datetime:
    """Cycle hours are 00/06/12/18 UTC; a cycle is only assumed published
    `publish_latency_minutes` after its run time (GFS 0.25deg typically finishes
    ~3.5-4h after cycle time - see config.publish_latency_minutes).
    """
    anchor = now - timedelta(minutes=publish_latency_minutes)
    candidates = sorted(cycles)
    best = None
    for h in candidates:
        candidate = anchor.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate <= anchor and (best is None or candidate > best):
            best = candidate
    if best is None:
        # anchor is before today's first cycle hour - fall back to yesterday's last cycle
        best = (anchor - timedelta(days=1)).replace(hour=max(candidates), minute=0, second=0, microsecond=0)
    return best


class NomadsGfsDataSource(NWPDataSource):
    """Real adapter: NOAA NOMADS GFS 0.25deg GRIB filter/subset service - public
    domain US government data, no credentials required, no robots.txt restriction.
    See README "Data source & ToS" for the compliance check performed before this
    was written.
    """

    SOURCE_NAME = "noaa-nomads-gfs-0p25"

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient, rate_limiter: RateLimiter,
        bbox: FetchBBox | None = None, target_latitude: float | None = None, target_longitude: float | None = None,
    ):
        self._settings = settings
        self._client = client
        self._rate_limiter = rate_limiter
        self._bbox = bbox or nong_fab_fetch_bbox(settings.bbox_padding_deg)
        self._target_lat = target_latitude if target_latitude is not None else settings.site_latitude
        self._target_lon = target_longitude if target_longitude is not None else settings.site_longitude

    async def fetch_latest_cycle(self) -> list[tuple[RawFetchResult, NWPForecastPoint]]:
        cycle_issue_time = await self._find_latest_published_cycle()

        results: list[tuple[RawFetchResult, NWPForecastPoint]] = []
        for fhour in self._settings.forecast_hours:
            raw = await self._fetch_one_with_retry(cycle_issue_time, fhour)
            point = await asyncio.to_thread(_decode_grib_sync, raw.body, self._target_lat, self._target_lon, self.SOURCE_NAME)
            results.append((raw, point))
        return results

    async def _find_latest_published_cycle(self) -> datetime:
        """Walks backward through cycles (starting after the expected publish
        latency) until one is confirmed present via a HEAD request on its f000 .idx file.
        """
        settings = self._settings
        now = datetime.now(timezone.utc)
        anchor = _most_recent_published_cycle(now, settings.gfs_cycles, settings.publish_latency_minutes)

        cycle_hours_desc = sorted(settings.gfs_cycles, reverse=True)
        candidates: list[datetime] = []
        cursor = anchor
        for _ in range(settings.lookback_cycles + 1):
            candidates.append(cursor)
            idx = cycle_hours_desc.index(cursor.hour)
            if idx + 1 < len(cycle_hours_desc):
                cursor = cursor.replace(hour=cycle_hours_desc[idx + 1])
            else:
                cursor = (cursor - timedelta(days=1)).replace(hour=cycle_hours_desc[0])

        for candidate in candidates:
            dir_path = settings.nomads_prod_dir_template.format(date=candidate, cycle=candidate.hour)
            file_name = settings.gfs_file_template.format(cycle=candidate.hour, fhour=0)
            idx_url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod{dir_path}/{file_name}.idx"

            await self._rate_limiter.wait()
            resp = await self._client.head(idx_url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
            if resp.status_code == 200:
                return candidate

        raise DataUnavailableError(f"no published GFS cycle found in the last {settings.lookback_cycles + 1} cycles (searched back from {anchor.isoformat()})")

    async def _fetch_one_with_retry(self, cycle_issue_time: datetime, forecast_hour: int) -> RawFetchResult:
        settings = self._settings
        url = _build_filter_url(settings, cycle_issue_time, forecast_hour, self._bbox)

        @retry(
            stop=stop_after_attempt(settings.max_retry_attempts),
            wait=wait_exponential(multiplier=settings.retry_backoff_base_seconds, max=settings.retry_backoff_max_seconds),
            reraise=True,
        )
        async def _do_fetch() -> httpx.Response:
            await self._rate_limiter.wait()
            resp = await self._client.get(url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent})
            resp.raise_for_status()
            return resp

        resp = await _do_fetch()
        return RawFetchResult(
            url=url,
            fetched_at=datetime.now(timezone.utc),
            content_type="application/x-grib2",
            body=resp.content,
            issue_time=cycle_issue_time,
            forecast_hour=forecast_hour,
        )


class MockNWPDataSource(NWPDataSource):
    """Fixture-backed source for local dev and tests - the default
    (config.source_mode="mock"), decoding the same real sample GRIB2 file used by the
    unit tests so the pipeline is exercised against real bytes, not synthetic ones.
    """

    SOURCE_NAME = "mock-fixture"

    def __init__(self, settings: Settings, fixture_path: Path | None = None, forecast_hours: list[int] | None = None):
        self._settings = settings
        # nwp/src/nwp_ingestion/datasource.py -> nwp/fixtures/...
        package_root = Path(__file__).resolve().parent.parent.parent
        self._fixture_path = fixture_path or (package_root / "fixtures" / "sample_gfs_nongfab.grib2")
        self._forecast_hours = forecast_hours if forecast_hours is not None else [1]

    async def fetch_latest_cycle(self) -> list[tuple[RawFetchResult, NWPForecastPoint]]:
        grib_bytes = Path(self._fixture_path).read_bytes()
        now = datetime.now(timezone.utc)

        results: list[tuple[RawFetchResult, NWPForecastPoint]] = []
        for fhour in self._forecast_hours:
            point = await asyncio.to_thread(
                _decode_grib_sync, grib_bytes, self._settings.site_latitude, self._settings.site_longitude, self.SOURCE_NAME
            )
            raw = RawFetchResult(
                url="mock://nwp-fixture", fetched_at=now, content_type="application/x-grib2",
                body=grib_bytes, issue_time=point.issue_time, forecast_hour=fhour,
            )
            results.append((raw, point))
        return results


def build_datasource(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    rate_limiter: RateLimiter | None = None,
) -> NWPDataSource:
    if settings.source_mode == "mock":
        return MockNWPDataSource(settings)

    if client is None or rate_limiter is None:
        raise ValueError("http source mode requires an httpx client and a RateLimiter")
    return NomadsGfsDataSource(settings, client, rate_limiter)
