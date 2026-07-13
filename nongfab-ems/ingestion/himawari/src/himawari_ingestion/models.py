from datetime import datetime

from sqlalchemy import TIMESTAMP, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CloudObsORM(Base):
    """Maps to the `cloud_obs` hypertable created by db/migrations/0001_cloud_obs.sql."""

    __tablename__ = "cloud_obs"

    time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    cloud_opacity_pct: Mapped[float] = mapped_column(Float)
    cloud_index: Mapped[float] = mapped_column(Float)
    raw_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
