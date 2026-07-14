from datetime import datetime

from sqlalchemy import TIMESTAMP, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CloudObsORM(Base):
    """Maps to the `cloud_obs` hypertable created by db/migrations/0001_cloud_obs.sql.

    One row per timestamp = the value sampled at Nong Fab's own coordinate, derived
    from the tile in cloud_raster_frames - kept for simple point-time-series consumers.
    """

    __tablename__ = "cloud_obs"

    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    cloud_opacity_pct: Mapped[float] = mapped_column(Float)
    cloud_index: Mapped[float] = mapped_column(Float)
    raw_object_key: Mapped[str | None] = mapped_column(String, nullable=True)


class CloudRasterFrameORM(Base):
    """Maps to the `cloud_raster_frames` hypertable created by
    db/migrations/0002_cloud_raster_frames.sql. The pixel arrays themselves live in
    MinIO (raster_object_key); this table is a lightweight, queryable index over them.
    """

    __tablename__ = "cloud_raster_frames"

    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    lat_min: Mapped[float] = mapped_column(Float)
    lat_max: Mapped[float] = mapped_column(Float)
    lon_min: Mapped[float] = mapped_column(Float)
    lon_max: Mapped[float] = mapped_column(Float)
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)
    nong_fab_cloud_opacity_pct: Mapped[float] = mapped_column(Float)
    nong_fab_cloud_index: Mapped[float] = mapped_column(Float)
    motion_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    motion_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    raster_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
