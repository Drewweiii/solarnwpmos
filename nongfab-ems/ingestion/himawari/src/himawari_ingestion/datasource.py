from __future__ import annotations

import asyncio
import io
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import httpx
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential

from .compliance import RateLimiter
from .config import Settings
from .geolocation import NONG_FAB_BBOX, NONG_FAB_PIXEL, CalibratedBBox, CalibratedPixel, local_index_within_bbox
from .schemas import CloudRasterFrame, RawFetchResult

logger = logging.getLogger(__name__)

_S3_LIST_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class CloudDataSource(ABC):
    """Adapter interface so the ingestion pipeline can swap data providers later
    without touching the scheduler or storage layer.
    """

    @abstractmethod
    async def fetch_latest(self) -> tuple[RawFetchResult, CloudRasterFrame]:
        """Return the raw tile payload (an .npz - for audit/replay/CNN-LSTM training)
        and its validated metadata.
        """


class DataUnavailableError(RuntimeError):
    """No published NOAA AHI-L2-FLDK-Clouds file was found within the configured lookback window."""


def _parse_list_bucket_keys(xml_text: str) -> list[str]:
    root = ElementTree.fromstring(xml_text)
    return [el.text for el in root.iter(f"{_S3_LIST_NS}Key") if el.text]


def serialize_raster(cloud_mask: np.ndarray, cloud_probability: np.ndarray, latitude: np.ndarray, longitude: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, cloud_mask=cloud_mask, cloud_probability=cloud_probability, latitude=latitude, longitude=longitude)
    return buf.getvalue()


def deserialize_raster(body: bytes) -> dict[str, np.ndarray]:
    with np.load(io.BytesIO(body)) as npz:
        return {k: npz[k] for k in npz.files}


def _build_raster_frame(
    cloud_mask: np.ndarray, cloud_probability: np.ndarray, bbox: CalibratedBBox, nong_fab_local: tuple[int, int],
    observed_at: datetime, source: str,
) -> CloudRasterFrame:
    """CloudMask (flag values 0=clear, 1=probably_clear, 2=probably_cloudy, 3=cloudy) and
    CloudProbability (continuous 0-1) are NOAA/NESDIS's real field names in the
    AHI-CMSK product - verified live 2026-07-14 by opening an actual file, not guessed.
    Neither is literally called "opacity", so this maps CloudProbability (the closest
    continuous analog) to *_cloud_opacity_pct, and the categorical CloudMask normalized
    to [0, 1] to *_cloud_index.
    """
    lr, lc = nong_fab_local
    rows, cols = bbox.shape
    return CloudRasterFrame(
        observed_at=observed_at,
        source=source,
        lat_min=bbox.lat_min, lat_max=bbox.lat_max, lon_min=bbox.lon_min, lon_max=bbox.lon_max,
        rows=rows, cols=cols,
        nong_fab_cloud_opacity_pct=min(100.0, max(0.0, float(cloud_probability[lr, lc]) * 100.0)),
        nong_fab_cloud_index=min(1.5, max(-0.2, float(cloud_mask[lr, lc]) / 3.0)),
    )


def _read_raster_sync(url: str, bbox: CalibratedBBox) -> dict[str, np.ndarray]:
    """Blocking: opens the remote NetCDF lazily (fsspec+h5netcdf) and reads only the
    HDF5 chunk(s) covering the bbox window via HTTP range requests - not the whole file.
    Must run off the event loop - see HimawariAHICloudSource._read_raster.
    """
    import fsspec
    import xarray as xr

    with fsspec.open(url, mode="rb") as f:
        ds = xr.open_dataset(f, engine="h5netcdf")
        window = ds[["CloudMask", "CloudProbability"]].isel(
            Rows=slice(bbox.row_start, bbox.row_end + 1), Columns=slice(bbox.col_start, bbox.col_end + 1)
        ).load()
        return {
            "cloud_mask": window["CloudMask"].values,
            "cloud_probability": window["CloudProbability"].values,
            "latitude": window["Latitude"].values,
            "longitude": window["Longitude"].values,
        }


class HimawariAHICloudSource(CloudDataSource):
    """Real adapter: NOAA/NESDIS AHI-L2-FLDK-Clouds (Cloud Mask) product, published on
    AWS Open Data (s3://noaa-himawari9) as part of the NOAA Big Data Program - public
    domain US government data, publicly readable over plain HTTPS with no credentials
    and no robots.txt/ToS gate to check (it's a documented open-data distribution
    endpoint, not a scraped website). See module README "Data source" for how the
    target bbox and field mapping were verified against a live file.
    """

    SOURCE_NAME = "noaa-himawari9-ahi-cmsk"

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient, rate_limiter: RateLimiter,
        bbox: CalibratedBBox = NONG_FAB_BBOX, pixel: CalibratedPixel = NONG_FAB_PIXEL,
    ):
        self._settings = settings
        self._client = client
        self._rate_limiter = rate_limiter
        self._bbox = bbox
        self._nong_fab_local = local_index_within_bbox(bbox, pixel)

    async def fetch_latest(self) -> tuple[RawFetchResult, CloudRasterFrame]:
        anchor = datetime.now(timezone.utc) - timedelta(minutes=self._settings.publish_latency_minutes)
        return await self.fetch_at(anchor)

    async def fetch_at(self, anchor: datetime) -> tuple[RawFetchResult, CloudRasterFrame]:
        """Fetches the most recent published frame at-or-before `anchor` - `fetch_latest`
        is just `fetch_at(now - publish_latency)`. The separate entry point is what
        `backfill.py` calls with a past timestamp to seed cold-start history (Module 4
        needs real accumulated data, not just live-forward polling from here on - see
        root README "Known gaps").
        """
        key, observed_at = await self._find_object_key_at_or_before(anchor)
        url = f"https://{self._settings.noaa_bucket}.s3.amazonaws.com/{key}"

        arrays = await self._read_raster_with_retry(url)

        raw = RawFetchResult(
            url=url,
            fetched_at=datetime.now(timezone.utc),
            content_type="application/octet-stream",
            body=serialize_raster(arrays["cloud_mask"], arrays["cloud_probability"], arrays["latitude"], arrays["longitude"]),
        )
        frame = _build_raster_frame(
            arrays["cloud_mask"], arrays["cloud_probability"], self._bbox, self._nong_fab_local, observed_at, self.SOURCE_NAME
        )
        return raw, frame

    async def _find_object_key_at_or_before(self, anchor: datetime) -> tuple[str, datetime]:
        """Walks backward in 10-min steps from `anchor` until a folder containing a
        CMSK file is found. `fetch_latest`'s anchor is `now - publish_latency`
        (the file may not be published yet); `backfill.py`'s anchor is an arbitrary
        past timestamp (always published by now, but the exact 10-min slot the
        product landed in can still be off by one step - same walk-back handles both).
        """
        settings = self._settings
        slot = anchor.replace(minute=anchor.minute - anchor.minute % 10, second=0, microsecond=0)

        for i in range(settings.lookback_slots):
            candidate = slot - timedelta(minutes=10 * i)
            prefix = f"{settings.noaa_product_prefix}/{candidate:%Y/%m/%d/%H%M}/"

            await self._rate_limiter.wait()
            list_url = f"https://{settings.noaa_bucket}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
            resp = await self._client.get(
                list_url, timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent}
            )
            resp.raise_for_status()

            match = next((k for k in _parse_list_bucket_keys(resp.text) if settings.noaa_file_prefix in k), None)
            if match:
                return match, candidate

        raise DataUnavailableError(
            f"no {settings.noaa_file_prefix} file found in the last {settings.lookback_slots} 10-min slots "
            f"(searched back from {slot.isoformat()})"
        )

    async def _read_raster_with_retry(self, url: str) -> dict[str, np.ndarray]:
        settings = self._settings

        @retry(
            stop=stop_after_attempt(settings.max_retry_attempts),
            wait=wait_exponential(multiplier=settings.retry_backoff_base_seconds, max=settings.retry_backoff_max_seconds),
            reraise=True,
        )
        async def _do_read() -> dict[str, np.ndarray]:
            return await asyncio.to_thread(_read_raster_sync, url, self._bbox)

        return await _do_read()


class MockCloudDataSource(CloudDataSource):
    """Fixture-backed source for local dev and tests - the default (config.source_mode="mock"),
    so the rest of the pipeline is fully exercisable without depending on a live network call.
    Synthesizes a small raster the same shape as NONG_FAB_BBOX from the single-value fixture,
    with independent per-pixel jitter, so it exercises the tile/motion code paths realistically.
    """

    SOURCE_NAME = "mock-fixture"

    def __init__(
        self, settings: Settings, fixture_path: Path | None = None, jitter: bool = True,
        bbox: CalibratedBBox = NONG_FAB_BBOX, pixel: CalibratedPixel = NONG_FAB_PIXEL,
    ):
        self._settings = settings
        # himawari/src/himawari_ingestion/datasource.py -> himawari/fixtures/...
        package_root = Path(__file__).resolve().parent.parent.parent
        self._fixture_path = fixture_path or (package_root / "fixtures" / "sample_himawari_response.json")
        self._jitter = jitter
        self._bbox = bbox
        self._nong_fab_local = local_index_within_bbox(bbox, pixel)

    async def fetch_latest(self) -> tuple[RawFetchResult, CloudRasterFrame]:
        payload = json.loads(Path(self._fixture_path).read_text())
        now = datetime.now(timezone.utc)
        rows, cols = self._bbox.shape

        base_opacity = payload["cloud_opacity"] / 100.0  # -> probability [0,1]
        base_mask = round(payload["cloud_index"] * 3.0)  # -> nearest flag value [0,3]

        if self._jitter:
            cloud_probability = np.clip(base_opacity + np.random.uniform(-0.1, 0.1, size=(rows, cols)), 0.0, 1.0)
            cloud_mask = np.clip(base_mask + np.random.choice([-1, 0, 0, 0, 1], size=(rows, cols)), 0, 3).astype(float)
        else:
            cloud_probability = np.full((rows, cols), base_opacity)
            cloud_mask = np.full((rows, cols), float(base_mask))

        lat = np.linspace(self._bbox.lat_max, self._bbox.lat_min, rows)[:, None] * np.ones((1, cols))
        lon = np.linspace(self._bbox.lon_min, self._bbox.lon_max, cols)[None, :] * np.ones((rows, 1))

        body = serialize_raster(cloud_mask, cloud_probability, lat, lon)
        raw = RawFetchResult(url="mock://himawari-fixture", fetched_at=now, content_type="application/octet-stream", body=body)
        frame = _build_raster_frame(cloud_mask, cloud_probability, self._bbox, self._nong_fab_local, now, self.SOURCE_NAME)
        return raw, frame


def build_datasource(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    rate_limiter: RateLimiter | None = None,
) -> CloudDataSource:
    if settings.source_mode == "mock":
        return MockCloudDataSource(settings)

    if client is None or rate_limiter is None:
        raise ValueError("http source mode requires an httpx client and a RateLimiter")
    return HimawariAHICloudSource(settings, client, rate_limiter)
