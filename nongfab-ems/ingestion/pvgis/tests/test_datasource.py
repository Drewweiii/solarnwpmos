import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from pvgis_ingestion.config import Settings
from pvgis_ingestion.datasource import (
    DataUnavailableError,
    MockPVGISSource,
    PVGISDataSource,
    _parse_seriescalc_response,
    build_datasource,
)
from pvgis_ingestion.schemas import SOURCE_NAME

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "sample_seriescalc_response.json"


def test_parse_seriescalc_response_extracts_hourly_points():
    body = FIXTURE_PATH.read_bytes()
    points = _parse_seriescalc_response(body, 12.6834, 101.1199, "test")

    assert len(points) == 3
    first = points[0]
    assert first.valid_time == datetime(2020, 1, 1, 0, 30, tzinfo=timezone.utc)
    assert first.issue_time == first.valid_time  # historical reanalysis, not a forecast - see schemas.py
    assert first.ssrd_w_m2 == pytest.approx(122.75)
    assert first.temp2m_c == pytest.approx(24.79)
    assert first.wind10m_u_ms == pytest.approx(4.0)
    assert first.wind10m_v_ms == 0.0
    assert first.latitude == 12.6834 and first.longitude == 101.1199
    assert points == sorted(points, key=lambda p: p.valid_time)


def test_parse_seriescalc_response_every_row_has_zero_lead_hours():
    """The whole point of issue_time == valid_time: real_data.py's k-step lead-hour
    filter (lead_hours = valid_time - issue_time) must never match HOUR_LEAD_HOURS
    (1..6) for a PVGIS-sourced row - see backfill.py's own docstring."""
    body = FIXTURE_PATH.read_bytes()
    points = _parse_seriescalc_response(body, 12.6834, 101.1199, "test")
    assert all((p.valid_time - p.issue_time).total_seconds() == 0 for p in points)


@pytest.mark.asyncio
async def test_mock_source_returns_fixture_backed_points(settings):
    source = MockPVGISSource(settings, fixture_path=FIXTURE_PATH)
    raw, points = await source.fetch_year(2024)

    assert raw.content_type == "application/json"
    assert len(points) == 3
    assert all(p.valid_time.year == 2024 for p in points)  # reindexed onto the requested year
    assert all(p.source == "mock-fixture" for p in points)


@pytest.mark.asyncio
async def test_build_datasource_mock_mode(settings):
    source = build_datasource(settings)
    assert isinstance(source, MockPVGISSource)


def test_build_datasource_http_mode_requires_client(settings):
    settings.source_mode = "http"
    with pytest.raises(ValueError):
        build_datasource(settings)


@pytest.mark.asyncio
@respx.mock
async def test_pvgis_source_fetches_and_parses_real_shaped_response(settings):
    settings.source_mode = "http"
    respx.get(url__startswith=settings.base_url).mock(return_value=httpx.Response(200, content=FIXTURE_PATH.read_bytes()))

    async with httpx.AsyncClient() as client:
        source = PVGISDataSource(settings, client, target_latitude=12.68337, target_longitude=101.11987)
        raw, points = await source.fetch_year(2020)

    assert len(points) == 3
    assert all(p.source == SOURCE_NAME for p in points)
    assert all(p.latitude == 12.68337 and p.longitude == 101.11987 for p in points)


@pytest.mark.asyncio
@respx.mock
async def test_pvgis_source_raises_when_year_is_entirely_missing(settings):
    settings.source_mode = "http"
    empty_body = b'{"inputs": {}, "outputs": {"hourly": []}, "meta": {}}'
    respx.get(url__startswith=settings.base_url).mock(return_value=httpx.Response(200, content=empty_body))

    async with httpx.AsyncClient() as client:
        source = PVGISDataSource(settings, client)
        with pytest.raises(DataUnavailableError):
            await source.fetch_year(2020)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("PVGIS_LIVE_TEST") != "1",
    reason="set PVGIS_LIVE_TEST=1 to hit the real PVGIS API - NOT reachable from this dev sandbox "
    "(confirmed reachable from the Railway deployment 2026-07-16 - see README)",
)
@pytest.mark.asyncio
async def test_pvgis_datasource_against_real_api():
    settings = Settings(source_mode="http")
    async with httpx.AsyncClient() as client:
        source = PVGISDataSource(settings, client)
        raw, points = await source.fetch_year(settings.year)

    assert len(points) > 8000  # a full (non-leap) year of hourly data
    assert all(0 <= p.ssrd_w_m2 <= 1500 for p in points)
