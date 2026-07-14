import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from himawari_ingestion.compliance import RateLimiter
from himawari_ingestion.datasource import (
    DataUnavailableError,
    HimawariAHICloudSource,
    MockCloudDataSource,
    _map_ahi_cmsk_to_observation,
    _parse_list_bucket_keys,
    build_datasource,
)
from himawari_ingestion.geolocation import CalibratedPixel

BUCKET_URL = "https://noaa-himawari9.s3.amazonaws.com"

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


def test_map_ahi_cmsk_to_observation_scales_probability_and_normalizes_mask():
    obs = _map_ahi_cmsk_to_observation(
        cloud_mask=3.0, cloud_probability=0.999, lat=12.71, lon=101.15,
        observed_at=datetime(2026, 7, 13, 2, 0, tzinfo=timezone.utc), source="noaa-himawari9-ahi-cmsk",
    )
    assert obs.cloud_opacity_pct == pytest.approx(99.9)
    assert obs.cloud_index == pytest.approx(1.0)


def test_map_ahi_cmsk_clear_sky():
    obs = _map_ahi_cmsk_to_observation(
        cloud_mask=0.0, cloud_probability=0.02, lat=12.71, lon=101.15,
        observed_at=datetime(2026, 7, 13, 2, 0, tzinfo=timezone.utc), source="noaa-himawari9-ahi-cmsk",
    )
    assert obs.cloud_opacity_pct == pytest.approx(2.0)
    assert obs.cloud_index == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_mock_datasource_returns_observation_at_configured_site(settings):
    source = MockCloudDataSource(settings, jitter=False)
    raw, observation = await source.fetch_latest()

    assert observation.latitude == settings.site_latitude
    assert observation.longitude == settings.site_longitude
    assert observation.source == "mock-fixture"
    assert raw.content_type == "application/json"
    assert json.loads(raw.body)["cloud_opacity"] == observation.cloud_opacity_pct


@pytest.mark.asyncio
async def test_build_datasource_mock_mode(settings):
    source = build_datasource(settings)
    assert isinstance(source, MockCloudDataSource)


@pytest.mark.asyncio
@respx.mock
async def test_ahi_source_finds_latest_and_reads_pixel(settings):
    settings.source_mode = "http"
    settings.publish_latency_minutes = 0
    respx.get(url__startswith=f"{BUCKET_URL}/?list-type=2").mock(return_value=httpx.Response(200, text=LIST_BUCKET_XML))

    fake_pixel_data = {"cloud_mask": 3.0, "cloud_probability": 0.95, "latitude": 12.708836, "longitude": 101.14675}

    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0), pixel=CalibratedPixel(2086, 859, 12.708836, 101.14675))
        with patch("himawari_ingestion.datasource.asyncio.to_thread", new=AsyncMock(return_value=fake_pixel_data)) as mocked:
            raw, observation = await source.fetch_latest()

    assert mocked.called
    assert observation.cloud_opacity_pct == pytest.approx(95.0)
    assert observation.cloud_index == pytest.approx(1.0)
    assert observation.source == "noaa-himawari9-ahi-cmsk"
    manifest = json.loads(raw.body)
    assert manifest["row"] == 2086 and manifest["col"] == 859
    assert "AHI-CMSK" in manifest["source_url"]


@pytest.mark.asyncio
@respx.mock
async def test_ahi_source_raises_when_no_file_published_within_lookback(settings):
    settings.source_mode = "http"
    settings.lookback_slots = 3
    respx.get(url__startswith=f"{BUCKET_URL}/?list-type=2").mock(return_value=httpx.Response(200, text=EMPTY_LIST_BUCKET_XML))

    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0))
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

    fake_pixel_data = {"cloud_mask": 1.0, "cloud_probability": 0.3, "latitude": 12.7, "longitude": 101.1}
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.0))
        with patch("himawari_ingestion.datasource.asyncio.to_thread", new=AsyncMock(return_value=fake_pixel_data)):
            raw, observation = await source.fetch_latest()

    assert route.call_count == 2
    assert observation.cloud_opacity_pct == pytest.approx(30.0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ahi_source_end_to_end_against_real_noaa_bucket(settings, require_live_noaa):
    """Skipped unless RUN_LIVE_NOAA_TESTS=1 - hits the real public NOAA bucket
    (no credentials needed) and reads one real pixel. Confirms the calibrated
    NONG_FAB_PIXEL constant still lines up with a live file's grid.
    """
    settings.source_mode = "http"
    async with httpx.AsyncClient() as client:
        source = HimawariAHICloudSource(settings, client, RateLimiter(0.5))
        raw, observation = await source.fetch_latest()

    assert 0 <= observation.cloud_opacity_pct <= 100
    assert -0.2 <= observation.cloud_index <= 1.5
    assert abs(observation.latitude - settings.site_latitude) < 0.05
    assert abs(observation.longitude - settings.site_longitude) < 0.05
