"""
backend/app/db/models.py
SQLAlchemy 2.0 (async) models for the Nong Fab EMS on TimescaleDB.

TimescaleDB notes
-----------------
After `Base.metadata.create_all`, convert the time-series tables to hypertables:

    SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);
    SELECT create_hypertable('weather_forecast', 'valid_time', if_not_exists => TRUE);
    SELECT create_hypertable('solar_prediction', 'target_time', if_not_exists => TRUE);

Then add continuous aggregates (e.g. 15-min buckets) + compression/retention policies.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class SiteStatus(str, enum.Enum):
    installed = "installed"
    designed = "designed"


class HorizonType(str, enum.Enum):
    minute_ahead = "minute_ahead"   # < 120 min
    hour_ahead = "hour_ahead"       # 1-6 h
    day_ahead = "day_ahead"         # 1-7 d


class WeatherSource(str, enum.Enum):
    himawari = "himawari"           # satellite cloud index/opacity
    gfs = "gfs"                     # NOAA NWP
    open_meteo = "open_meteo"
    ecmwf = "ecmwf"


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class Site(Base):
    """One PV installation point. Capacities are config-driven (seed from SLD)."""
    __tablename__ = "site"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)   # 'ISB', 'GIS', 'SITE3'
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[SiteStatus] = mapped_column(Enum(SiteStatus))
    latitude: Mapped[float] = mapped_column(Float, default=12.6500)
    longitude: Mapped[float] = mapped_column(Float, default=101.1400)

    dc_capacity_kwp: Mapped[float] = mapped_column(Float)        # ISB 140.14 / GIS 60.06
    ac_capacity_kw: Mapped[float] = mapped_column(Float)         # ISB 150 / GIS 50
    inverter_clip_kw: Mapped[float] = mapped_column(Float)       # hard AC cap for clip-aware conversion
    tilt_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    azimuth_deg: Mapped[float | None] = mapped_column(Float, nullable=True)

    telemetry: Mapped[list["Telemetry"]] = relationship(back_populates="site")
    predictions: Mapped[list["SolarPrediction"]] = relationship(back_populates="site")

    @property
    def dc_ac_ratio(self) -> float:
        return self.dc_capacity_kwp / self.ac_capacity_kw

    @property
    def clips(self) -> bool:
        """GIS (1.20) clips; ISB (0.93) does not."""
        return self.dc_ac_ratio > 1.0


# ---------------------------------------------------------------------------
# Time-series (hypertables)
# ---------------------------------------------------------------------------
class Telemetry(Base):
    """Live SCADA / inverter measurements (+ plant-level GTG/grid context)."""
    __tablename__ = "telemetry"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id"), primary_key=True)

    p_ac_kw: Mapped[float] = mapped_column(Float)                    # measured AC power
    p_dc_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    irradiance_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)  # on-site pyranometer if any
    module_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    inverter_ok: Mapped[bool] = mapped_column(Boolean, default=True)

    # plant-level context (nullable; only on aggregate rows)
    gtg_output_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    grid_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_load_kw: Mapped[float | None] = mapped_column(Float, nullable=True)

    site: Mapped["Site"] = relationship(back_populates="telemetry")

    __table_args__ = (Index("ix_telemetry_site_time", "site_id", "time"),)


class WeatherForecast(Base):
    """Exogenous weather features from satellite/NWP providers."""
    __tablename__ = "weather_forecast"

    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    source: Mapped[WeatherSource] = mapped_column(Enum(WeatherSource), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    # NWP block (GFS DSWRF etc.)
    ssrd_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)   # DSWRF
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Satellite block (Himawari)
    cloud_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_opacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    # synthesized
    clearsky_ghi_wm2: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_wx_source_valid", "source", "valid_time"),)


class SolarPrediction(Base):
    """Model output with prediction interval + derived reserve requirement."""
    __tablename__ = "solar_prediction"

    target_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("site.id"), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    horizon_type: Mapped[HorizonType] = mapped_column(Enum(HorizonType), primary_key=True)

    model_name: Mapped[str] = mapped_column(String(48))         # 'lightgbm', 'neuralprophet', 'cnn_lstm'
    lead_minutes: Mapped[int] = mapped_column(Integer)

    p_hat_kw: Mapped[float] = mapped_column(Float)              # point forecast
    p_lower_kw: Mapped[float | None] = mapped_column(Float, nullable=True)   # p10
    p_upper_kw: Mapped[float | None] = mapped_column(Float, nullable=True)   # p90
    pi_nominal: Mapped[float | None] = mapped_column(Float, nullable=True)   # e.g. 0.80

    spinning_reserve_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped["Site"] = relationship(back_populates="predictions")

    __table_args__ = (Index("ix_pred_site_target", "site_id", "target_time"),)
