import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import numpy as np
import pytest
import respx

from himawari_ingestion.compliance import RateLimiter
from himawari_ingestion.config import Settings
from himawari_ingestion.datasource import (
    DataUnavailableError,
    HimawariAHICloudSource,
    MockCloudDataSource,
    _build_raster_frame,
    _parse_list_bucket_keys,
    build_datasource,
    deserialize_raster,
    serialize_raster,
)
from himawari_ingestion.geolocation import CalibratedBBox, CalibratedPixel

BUCKET_URL = "https://noaa-himawari9.s3.amazonaws.com"
TEST_BBOX = CalibratedBBox(row_start=0, row_end=2, col_start=0, col_end=1, lat_min=12.61, lat_max=12.74, lon_min=101.06, lon_max=101.18)
TEST_PIXEL = CalibratedPixel(row=1, col=1, latitude=12.7, longitude=101.1)

LIST_BUCKET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>noaa-himawari9</Name>
  <Contents><Key>AHI-L2-FLDK-Clouds/2026/07/13/0200/AHI-CHGT_v1r1_h09_x.nc</Key></Contents>
  <Contents><Key>AHI-L2-FLDK-Clouds/2026/07/13/0200/AHI-CMSK_v1r1_h09_s202607130200209_e202607130209403_c1.nc</Key></Contents>
  <Contents><Key>AHI-L2-FLDK-Clouds/2026/07/13/0200/AHI-CPHS_v1r1_h09_x.nc</Key></Contents>
</ListBucketResult>"""

EMPTY_LIST_BUCKET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>noaa-himawari9</Name>
</ListBucketResult>"""


def test_parse_list_bucket_keys_extracts_object_keys():
    keys = _parse_list_bucket_keys(LIST_BUCKET_XML)
    assert len(keys) == 3
    assert any("AHI-CMSK" in k for k in keys)


def test_serialize_deserialize_raster_roundtrips():
    cloud_mask = np.array([[0.0, 1.0], [2.0, 3.0]])
    cloud_probability = np.array([[0.1, 0.4], [0.6, 0.99]])
    lat = np.array([[12.7, 12.7], [12.68, 12.68]])
    lon = np.array([[101.1, 101.12], [101.1, 101.12]])

    body = serialize_raster(cloud_mask, cloud_probability, lat, lon)
    arrays = deserialize_raster(body)

    np.testing.assert_array_equal(arrays["cloud_mask"], cloud_mask)
    np.testing.assert_array_equal(arrays["cloud_probability"], cloud_probability)


def test_build_raster_frame_samples_nong_fab_pixel_from_tile():
    cloud_mask = np.zeros((3, 2))
    cloud_probability = np.zeros((3, 2))
    cloud_mask[1, 1] = 3.0
    cloud_probability[1, 1] = 0.95

    frame = _build_raster_frame(
        cloud_mask, cloud_probability, TEST_BBOX, nong_fab_local=(1, 1),
        observed_at=datetime(2026, 7, 13, 2, 0, tzinfo=timezone.utc), source="noaa-himawari9-ahi-cmsk",
    )

    assert frame.nong_fab_cloud_opacity_pct == pytest.approx(95.0)
    assert frame.nong_fab_cloud_index == pytest.approx(1.0)
    assert frame.rows == 3 and frame.cols == 2
    assert frame.lat_min == TEST_BBOX.lat_min and frame.lon_max == TEST_BBOX.lon_max


@pytest.mark.asyncio
async def test_mock_datasource_returns_tile_shaped_like_bbox(settings):
    source = MockCloudDataSource(settings, jitter=False, bbox=TEST_BBOX, pixel=TEST_PIXEL)
    raw, frame = await source.fetch_latest()

    assert (frame.rows, frame.cols) == TEST_BBOX.shape
    assert frame.source == "mock-fixture"
    assert raw.content_type == "application/octet-stream"

    arrays = deserialize_raster(raw.body)
    assert arrays["cloud_probability"].shape == TEST_BBOX.shape
    assert arrays["cloud_mask"].shape == TEST_BBOX.shape


@pytest.mark.asyncio
async def test_mock_datasource_jitter_varies_between_calls(settings):
    source = MockCloudDataSource(settings, jitter=True, bbox=TEST_BBOX, pixel=TEST_PIXEL)
    _, frame1 = await source.fetch_latest()
    _, frame2 = await source.fetch_latest()
    assert frame1.nong_fab_cloud_opacity_pct != frame2.nong_fab_cloud_opacity_pct


@pytest.mark.asyncio
async def test_build_datasource_mock_mode(settings):
    source = build_datasource(settings)
    assert isinstance(source, MockCloudDataSource)


@pytest.mark.asyncio
@respx.mock
async def test_ahi_source_finds_latest_and_reads_tile(settings):
    settings.source_mode = "http"
    settings.publish_latency_minutes = 0
    respx.get(url__startswith=f"{BUCKET_URL}/?list-type=2").mock(return_value=httpx.Response(200, text=LIST_BUCKET_XML))

    fake_arrays = {
        "cloud_mask": np.full(TEST_BBOX.shape, 3.0),
        "cloud_probability": np.full(TEST_BBOX.shape, 0.95),
        "latitude": np.full(TEST_BBOX.shape, 12.7),
        "longitude": np.full(TEST_BBOX.shape, 101.1),
    }

    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0), bbox=TEST_BBOX, pixel=TEST_PIXEL)
        with patch("himawari_ingestion.datasource.asyncio.to_thread", new=AsyncMock(return_value=fake_arrays)) as mocked:
            raw, frame = await source.fetch_latest()

    assert mocked.called
    assert frame.nong_fab_cloud_opacity_pct == pytest.approx(95.0)
    assert frame.nong_fab_cloud_index == pytest.approx(1.0)
    assert frame.source == "noaa-himawari9-ahi-cmsk"
    arrays = deserialize_raster(raw.body)
    assert arrays["cloud_probability"].shape == TEST_BBOX.shape


@pytest.mark.asyncio
@respx.mock
async def test_ahi_source_raises_when_no_file_published_within_lookback(settings):
    settings.source_mode = "http"
    settings.lookback_slots = 3
    respx.get(url__startswith=f"{BUCKET_URL}/?list-type=2").mock(return_value=httpx.Response(200, text=EMPTY_LIST_BUCKET_XML))

    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0), bbox=TEST_BBOX, pixel=TEST_PIXEL)
        with pytest.raises(DataUnavailableError):
            await source.fetch_latest()


@pytest.mark.asyncio
@respx.mock
async def test_ahi_source_walks_back_through_slots_until_file_found(settings):
    settings.source_mode = "http"
    settings.lookback_slots = 3

    route = respx.get(url__startswith=f"{BUCKET_URL}/?list-type=2")
    route.side_effect = [
        httpx.Response(200, text=EMPTY_LIST_BUCKET_XML),  # most recent slot: not published yet
        httpx.Response(200, text=LIST_BUCKET_XML),  # one slot back: found
    ]

    fake_arrays = {
        "cloud_mask": np.full(TEST_BBOX.shape, 1.0),
        "cloud_probability": np.full(TEST_BBOX.shape, 0.3),
        "latitude": np.full(TEST_BBOX.shape, 12.7),
        "longitude": np.full(TEST_BBOX.shape, 101.1),
    }
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0), bbox=TEST_BBOX, pixel=TEST_PIXEL)
        with patch("himawari_ingestion.datasource.asyncio.to_thread", new=AsyncMock(return_value=fake_arrays)):
            raw, frame = await source.fetch_latest()

    assert route.call_count == 2
    assert frame.nong_fab_cloud_opacity_pct == pytest.approx(30.0)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_at_reads_the_slot_nearest_the_given_anchor_not_now(settings):
    """fetch_at(anchor) with a past anchor must query the *anchor's* 10-min slot,
    not "now" - this is what backfill.py relies on to fetch arbitrary history.
    """
    settings.source_mode = "http"
    route = respx.get(url__startswith=f"{BUCKET_URL}/?list-type=2")
    route.mock(return_value=httpx.Response(200, text=LIST_BUCKET_XML))  # matches .../13/0200/ prefix

    fake_arrays = {
        "cloud_mask": np.full(TEST_BBOX.shape, 2.0),
        "cloud_probability": np.full(TEST_BBOX.shape, 0.5),
        "latitude": np.full(TEST_BBOX.shape, 12.7),
        "longitude": np.full(TEST_BBOX.shape, 101.1),
    }
    anchor = datetime(2026, 7, 13, 2, 7, tzinfo=timezone.utc)  # a past timestamp, not "now"
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0), bbox=TEST_BBOX, pixel=TEST_PIXEL)
        with patch("himawari_ingestion.datasource.asyncio.to_thread", new=AsyncMock(return_value=fake_arrays)):
            raw, frame = await source.fetch_at(anchor)

    requested_prefix = route.calls[0].request.url.params["prefix"]
    assert "2026/07/13/0200" in requested_prefix  # anchor rounds down to its own 10-min slot, not today's
    assert frame.observed_at == datetime(2026, 7, 13, 2, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fetch_latest_delegates_to_fetch_at_with_publish_latency_applied(settings):
    settings.publish_latency_minutes = 55
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0), bbox=TEST_BBOX, pixel=TEST_PIXEL)
        with patch.object(source, "fetch_at", new=AsyncMock(return_value=("raw", "frame"))) as mocked:
            result = await source.fetch_latest()

    assert result == ("raw", "frame")
    (called_anchor,) = mocked.call_args.args
    lag = datetime.now(timezone.utc) - called_anchor
    assert 54 <= lag.total_seconds() / 60 <= 56  # ~publish_latency_minutes ago, not "now"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_LIVE_NOAA_TESTS") != "1", reason="set RUN_LIVE_NOAA_TESTS=1 to hit the real NOAA S3 bucket")
@pytest.mark.asyncio
async def test_fetch_at_against_real_noaa_bucket_for_a_past_date():
    from datetime import timedelta

    settings = Settings(source_mode="http", min_seconds_between_requests=0.5)
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.5))
        anchor = datetime.now(timezone.utc) - timedelta(days=3)
        raw, frame = await source.fetch_at(anchor)

    assert frame.observed_at <= anchor
    assert (anchor - frame.observed_at) < timedelta(hours=1)
    assert 0 <= frame.nong_fab_cloud_opacity_pct <= 100
    assert len(raw.body) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ahi_source_end_to_end_against_real_noaa_bucket(settings, require_live_noaa):
    """Skipped unless RUN_LIVE_NOAA_TESTS=1 - hits the real public NOAA bucket
    (no credentials needed) and reads the real Nong Fab tile. Confirms
    NONG_FAB_BBOX still lines up with a live file's grid.
    """
    settings.source_mode = "http"
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.5))
        raw, frame = await source.fetch_latest()

    assert 0 <= frame.nong_fab_cloud_opacity_pct <= 100
    assert -0.2 <= frame.nong_fab_cloud_index <= 1.5
    assert (frame.rows, frame.cols) == (7, 6)
    arrays = deserialize_raster(raw.body)
    assert arrays["cloud_probability"].shape == (7, 6)
