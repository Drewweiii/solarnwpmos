"""
data-pipeline/providers.py
Pluggable data-source providers. Swap sources without touching the ML layer.

Celery beat schedule (data-pipeline/tasks.py):
    himawari:   every 10 min   (full-disk cadence)
    nwp/gfs:    every 6  hours  (00/06/12/18Z cycles)
    telemetry:  every 1  min    (SCADA/inverter)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime, timezone

# NONG FAB coordinates
LAT, LON = 12.6500, 101.1400


@dataclass
class WxRecord:
    valid_time: datetime
    issued_at: datetime
    source: str
    ssrd_wm2: float | None = None
    temp_c: float | None = None
    wind_ms: float | None = None
    rh_pct: float | None = None
    cloud_index: float | None = None
    cloud_opacity: float | None = None


class WeatherProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def fetch(self) -> list[WxRecord]:
        ...


# ---------------------------------------------------------------------------
# Satellite — Himawari cloud index / opacity (minute-ahead exogenous)
# ---------------------------------------------------------------------------
class HimawariAwsProvider(WeatherProvider):
    """
    RECOMMENDED default: NOAA Open Data on AWS (`noaa-himawari9`), anonymous S3,
    free & open with attribution. Read AHI bands, compute cloud index over the
    Rayong tile, derive motion vectors upstream in the CNN-LSTM feature builder.

    Alternatives (config-selectable): JAXA P-Tree (commercial use from 2026-02-01;
    account + no redistribution), NREL NSRDB Himawari API (historical, for training).
    """
    name = "himawari"

    def __init__(self, bucket: str = "noaa-himawari9", region: str = "ap-southeast-1"):
        self.bucket = bucket
        self.region = region

    async def fetch(self) -> list[WxRecord]:
        # import s3fs, xarray as xr  # anonymous=True
        # TODO: list latest full-disk key, open subregion tile around (LAT, LON),
        #       compute cloud_index/opacity, return one WxRecord for valid_time.
        raise NotImplementedError("Wire s3fs + xarray tile read for noaa-himawari9")


# ---------------------------------------------------------------------------
# NWP — NOAA GFS (hour & day-ahead exogenous)
# ---------------------------------------------------------------------------
class GfsNomadsProvider(WeatherProvider):
    """
    NOAA GFS via NOMADS grib-filter. Pull only the Rayong subregion + needed
    variables (DSWRF=SSRD, TMP, UGRD/VGRD→wind, RH). Parse GRIB2 with cfgrib.
    """
    name = "gfs"
    BASE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"

    def _url(self, cycle: str, fhr: int) -> str:
        date = cycle[:8]; hh = cycle[8:10]
        return (
            f"{self.BASE}?file=gfs.t{hh}z.pgrb2.0p25.f{fhr:03d}"
            "&var_DSWRF=on&var_TMP=on&var_UGRD=on&var_VGRD=on&var_RH=on"
            "&lev_surface=on&lev_2_m_above_ground=on&lev_10_m_above_ground=on"
            "&subregion=&leftlon=100&rightlon=102&toplat=13.5&bottomlat=12"
            f"&dir=/gfs.{date}/{hh}/atmos"
        )

    async def fetch(self) -> list[WxRecord]:
        # import httpx, cfgrib, xarray as xr
        # TODO: for fhr in range(1, 168): GET self._url(latest_cycle, fhr) → GRIB2 bytes
        #       → xr.open_dataset(..., engine="cfgrib") → nearest gridpoint to (LAT,LON)
        #       → WxRecord(ssrd_wm2=DSWRF, temp_c=TMP-273.15, wind_ms=hypot(U,V), rh_pct=RH)
        raise NotImplementedError("Wire httpx + cfgrib GFS subregion fetch")


class OpenMeteoProvider(WeatherProvider):
    """Easy JSON fallback. Check commercial terms before production use."""
    name = "open_meteo"
    URL = "https://api.open-meteo.com/v1/forecast"

    async def fetch(self) -> list[WxRecord]:
        # import httpx
        params = {
            "latitude": LAT, "longitude": LON,
            "hourly": "shortwave_radiation,temperature_2m,wind_speed_10m,relative_humidity_2m",
            "forecast_days": 7, "timezone": "UTC",
        }
        # r = await httpx.AsyncClient().get(self.URL, params=params); j = r.json()
        # issued = datetime.now(timezone.utc)
        # return [WxRecord(valid_time=parse(t), issued_at=issued, source=self.name,
        #                  ssrd_wm2=sw, temp_c=tmp, wind_ms=ws, rh_pct=rh) for ...]
        raise NotImplementedError("Wire httpx GET to Open-Meteo")


# ---------------------------------------------------------------------------
# Telemetry — mock generator for the PV plant (until SCADA is connected)
# ---------------------------------------------------------------------------
class TelemetryMockProvider:
    """
    Synthesizes plausible AC power for a site given a clear-sky bell + noise,
    applying inverter clipping for GIS (DC/AC 1.20). Replace with real SCADA tap.
    """
    def __init__(self, site_code: str, ac_cap_kw: float, dc_cap_kwp: float):
        self.site_code = site_code
        self.ac_cap_kw = ac_cap_kw
        self.dc_cap_kwp = dc_cap_kwp

    def sample(self, ts: datetime | None = None) -> dict:
        import math, random
        ts = ts or datetime.now(timezone.utc)
        hour = ts.hour + ts.minute / 60.0
        clearsky = max(0.0, math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
        cloud = random.uniform(0.6, 1.0)
        p_dc = self.dc_cap_kwp * clearsky * cloud
        p_ac = min(p_dc, self.ac_cap_kw)             # <-- clipping (matters for GIS)
        return {
            "time": ts, "site_code": self.site_code,
            "p_ac_kw": round(p_ac, 2), "p_dc_kw": round(p_dc, 2),
            "inverter_ok": True,
        }
