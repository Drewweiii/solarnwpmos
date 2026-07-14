from datetime import datetime

from sqlalchemy import TIMESTAMP, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NWPForecastORM(Base):
    """Maps to the `nwp_forecast` hypertable created by db/migrations/0003_nwp_forecast.sql.

    Keyed on (issue_time, valid_time, source) rather than just (valid_time, source):
    successive GFS cycles overlap in valid_time (e.g. the 00z run's f024 and the 06z
    run's f018 are both valid at the same instant), and forecast-engine training
    (Module 4) needs to reconstruct "what was known as of issue_time X", not just the
    latest overwrite - so every (issue_time, valid_time) pair is kept, not upserted
    over each other.
    """

    __tablename__ = "nwp_forecast"

    issue_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    valid_time: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    ssrd_w_m2: Mapped[float] = mapped_column(Float)
    temp2m_c: Mapped[float] = mapped_column(Float)
    wind10m_u_ms: Mapped[float] = mapped_column(Float)
    wind10m_v_ms: Mapped[float] = mapped_column(Float)
    relative_humidity_pct: Mapped[float] = mapped_column(Float)
    raw_object_key: Mapped[str | None] = mapped_column(String, nullable=True)
