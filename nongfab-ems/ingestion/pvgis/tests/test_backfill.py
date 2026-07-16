from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pvgis_ingestion.backfill import backfill_year
from pvgis_ingestion.datasource import DataUnavailableError, PVGISDataSource


@pytest.mark.asyncio
async def test_backfill_year_requests_settings_year_by_default(settings):
    settings.source_mode = "http"
    settings.year = 2019
    captured = {}

    async def fake_fetch_year(self, year):
        captured["year"] = year
        return object(), ["ok"]

    async with httpx.AsyncClient() as client:
        with patch.object(PVGISDataSource, "fetch_year", new=fake_fetch_year):
            result = await backfill_year(settings, client)

    assert result is not None
    assert captured["year"] == 2019


@pytest.mark.asyncio
async def test_backfill_year_accepts_an_explicit_year_override(settings):
    settings.source_mode = "http"
    captured = {}

    async def fake_fetch_year(self, year):
        captured["year"] = year
        return object(), ["ok"]

    async with httpx.AsyncClient() as client:
        with patch.object(PVGISDataSource, "fetch_year", new=fake_fetch_year):
            await backfill_year(settings, client, year=2021)

    assert captured["year"] == 2021


@pytest.mark.asyncio
async def test_backfill_year_returns_none_when_entirely_unavailable(settings):
    settings.source_mode = "http"

    async with httpx.AsyncClient() as client:
        with patch.object(PVGISDataSource, "fetch_year", new=AsyncMock(side_effect=DataUnavailableError("no data"))):
            result = await backfill_year(settings, client)

    assert result is None
