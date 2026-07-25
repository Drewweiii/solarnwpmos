"""Data-feed health and seasonal output anomalies (2026-07-25).

Two diagnostics the site had no way to ask for, both computable from data that is
genuinely measured:

1. **Feed health.** Every model input arrives from an external source on its own
   cadence (GFS hourly, Himawari ~10 min, Open-Meteo UV a few times a day, CAMS
   air-quality hourly). When one silently stops, the model keeps answering - it
   just quietly falls back to defaults, and nothing on the dashboard says so.
   That is exactly the failure mode of the aerosol bug fixed earlier the same day:
   the CAMS backfill ran once at boot with no refresh loop, so after three hours
   every aerosol feature reverted to a neutral constant and the only visible
   symptom was five cells reading "no data". These checks would have named it.

   Feeds come in two shapes, and conflating them would misreport both:
   - OBSERVATION feeds (satellite cloud, UV readings) are healthy when their
     NEWEST row is recent. Age is measured backwards from now.
   - COVERAGE feeds (NWP, aerosol - forecasts that legitimately extend into the
     future) are healthy when their newest row still reaches FORWARD of now by
     enough to serve the model's leads. A coverage feed whose newest row is only
     "recent" is already failing: it means the forward window has run out.

2. **Seasonal output anomalies.** A day's expected energy compared against the
   norm for that month, so an unusually poor stretch is visible rather than
   hidden inside an annual average. Causes are RANKED, not asserted: the module
   reports which measured driver deviated most from its own window median
   (cloud / rain / soiling / aerosol) and the caller must present that as an
   inference from the weather, since with no metered output there is no way to
   prove the array itself underperformed.

Pure: takes already-read values, returns verdicts. No store, no HTTP, no clock -
`now` is always passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Feed verdicts, worst last - `worst_status` relies on this ordering.
STATUS_OK = "ok"
STATUS_STALE = "stale"
STATUS_MISSING = "missing"
_SEVERITY = (STATUS_OK, STATUS_STALE, STATUS_MISSING)


@dataclass(frozen=True)
class FeedHealth:
    """One data feed's verdict.

    kind: 'observation' (newest row should be recent) or 'coverage' (newest row
        should reach forward of now).
    age_minutes: how far in the PAST the newest row is; negative for a coverage
        feed that reaches into the future (which is the healthy case).
    lead_minutes: how far FORWARD of now the newest row reaches; negative when
        the feed has fallen behind. None for an observation feed.
    """

    name: str
    kind: str
    status: str
    rows: int
    latest: datetime | None
    age_minutes: float | None
    lead_minutes: float | None
    limit_minutes: float
    detail: str


def _age_minutes(latest: datetime, now: datetime) -> float:
    return (now - latest).total_seconds() / 60


def evaluate_observation_feed(name: str, latest: datetime | None, rows: int, now: datetime, max_age_minutes: float) -> FeedHealth:
    """An observation feed is healthy while its newest row is younger than
    `max_age_minutes`."""
    if latest is None or rows == 0:
        return FeedHealth(
            name=name,
            kind="observation",
            status=STATUS_MISSING,
            rows=rows,
            latest=None,
            age_minutes=None,
            lead_minutes=None,
            limit_minutes=max_age_minutes,
            detail="ยังไม่มีข้อมูลในฐานข้อมูลเลย",
        )
    age = _age_minutes(latest, now)
    stale = age > max_age_minutes
    return FeedHealth(
        name=name,
        kind="observation",
        status=STATUS_STALE if stale else STATUS_OK,
        rows=rows,
        latest=latest,
        age_minutes=age,
        lead_minutes=None,
        limit_minutes=max_age_minutes,
        detail=(
            f"ข้อมูลล่าสุดเก่ากว่าที่ควร ({age:.0f} นาที > {max_age_minutes:.0f} นาที)"
            if stale
            else f"ข้อมูลล่าสุดอายุ {age:.0f} นาที"
        ),
    )


def evaluate_coverage_feed(name: str, latest: datetime | None, rows: int, now: datetime, min_lead_minutes: float) -> FeedHealth:
    """A coverage feed (a forecast series) is healthy while its newest row still
    reaches at least `min_lead_minutes` FORWARD of now. Falling behind that is
    what makes the model quietly substitute defaults for the leads it can no
    longer cover."""
    if latest is None or rows == 0:
        return FeedHealth(
            name=name,
            kind="coverage",
            status=STATUS_MISSING,
            rows=rows,
            latest=None,
            age_minutes=None,
            lead_minutes=None,
            limit_minutes=min_lead_minutes,
            detail="ยังไม่มีข้อมูลในฐานข้อมูลเลย",
        )
    lead = -_age_minutes(latest, now)
    short = lead < min_lead_minutes
    return FeedHealth(
        name=name,
        kind="coverage",
        status=STATUS_STALE if short else STATUS_OK,
        rows=rows,
        latest=latest,
        age_minutes=_age_minutes(latest, now),
        lead_minutes=lead,
        limit_minutes=min_lead_minutes,
        detail=(
            f"ครอบคลุมล่วงหน้าไม่พอ (ถึงอีก {lead:.0f} นาที, ต้องการ {min_lead_minutes:.0f} นาที)"
            if short
            else f"ครอบคลุมล่วงหน้าถึงอีก {lead:.0f} นาที"
        ),
    )


def worst_status(feeds: list[FeedHealth]) -> str:
    """The worst verdict across feeds - the one-word overall health. No feeds at
    all is itself 'missing', not 'ok'."""
    if not feeds:
        return STATUS_MISSING
    return max((f.status for f in feeds), key=_SEVERITY.index)


# --- Seasonal output anomalies ----------------------------------------------

# A day is flagged when its expected energy falls below this fraction of the
# month's own norm. 0.7 is a judgement call for "worth a look, not just weather
# noise", stated rather than tuned against anything.
ANOMALY_RATIO_THRESHOLD = 0.7


@dataclass(frozen=True)
class DayEnergy:
    """One day's expected energy plus the measured drivers for that day."""

    day: str  # ISO date
    energy_kwh: float
    cloud_pct: float | None = None
    precip_mm: float | None = None
    soiling_pct: float | None = None
    aod: float | None = None


@dataclass(frozen=True)
class OutputAnomaly:
    day: str
    energy_kwh: float
    norm_kwh: float
    ratio: float
    shortfall_kwh: float
    # The measured driver that deviated most from its window median, and a
    # human-readable reason. Ranked inference from the weather, NOT a proven
    # cause - there is no metered output to attribute against.
    likely_cause: str
    cause_detail: str


def _median(values: list[float]) -> float | None:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return None
    mid = len(clean) // 2
    return clean[mid] if len(clean) % 2 else (clean[mid - 1] + clean[mid]) / 2


def rank_cause(day: DayEnergy, days: list[DayEnergy]) -> tuple[str, str]:
    """Which measured driver was most adverse on `day` relative to the window's
    median. Returns (cause_key, Thai detail). 'unknown' when no driver was
    measured that day - deliberately, rather than blaming the nearest candidate.
    """
    candidates: list[tuple[float, str, str]] = []
    cloud_median = _median([d.cloud_pct for d in days if d.cloud_pct is not None])
    if day.cloud_pct is not None and cloud_median is not None and day.cloud_pct > cloud_median:
        candidates.append(((day.cloud_pct - cloud_median) / 100, "cloud", f"เมฆมากกว่าปกติ ({day.cloud_pct:.0f}% vs ปกติ {cloud_median:.0f}%)"))
    rain_median = _median([d.precip_mm for d in days if d.precip_mm is not None])
    if day.precip_mm is not None and rain_median is not None and day.precip_mm > rain_median:
        # Scaled against 20 mm as "a properly wet day" so it competes on a
        # comparable 0..1 footing with the fraction-based drivers above.
        candidates.append((min((day.precip_mm - rain_median) / 20, 1.0), "rain", f"ฝนมากกว่าปกติ ({day.precip_mm:.1f} mm vs ปกติ {rain_median:.1f} mm)"))
    soiling_median = _median([d.soiling_pct for d in days if d.soiling_pct is not None])
    if day.soiling_pct is not None and soiling_median is not None and day.soiling_pct > soiling_median:
        soiling_detail = f"คราบสกปรกสูงกว่าปกติ ({day.soiling_pct:.2f}% vs ปกติ {soiling_median:.2f}%)"
        candidates.append(((day.soiling_pct - soiling_median) / 100, "soiling", soiling_detail))
    aod_median = _median([d.aod for d in days if d.aod is not None])
    if day.aod is not None and aod_median is not None and day.aod > aod_median:
        candidates.append((min((day.aod - aod_median) / 0.5, 1.0), "aerosol", f"ฝุ่น/ละอองในอากาศสูงกว่าปกติ (AOD {day.aod:.2f} vs ปกติ {aod_median:.2f})"))
    if not candidates:
        return "unknown", "ยังไม่มีตัวแปรอากาศที่วัดได้ของวันนั้นมากพอจะระบุสาเหตุ"
    _, cause, detail = max(candidates, key=lambda c: c[0])
    return cause, detail


def find_output_anomalies(days: list[DayEnergy], norm_kwh: float, threshold: float = ANOMALY_RATIO_THRESHOLD) -> list[OutputAnomaly]:
    """Days whose expected energy fell below `threshold` x `norm_kwh`, newest
    first. A non-positive norm yields nothing (there is no baseline to be below),
    never a divide-by-zero."""
    if norm_kwh <= 0:
        return []
    found = []
    for day in days:
        ratio = day.energy_kwh / norm_kwh
        if ratio >= threshold:
            continue
        cause, detail = rank_cause(day, days)
        found.append(
            OutputAnomaly(
                day=day.day,
                energy_kwh=day.energy_kwh,
                norm_kwh=norm_kwh,
                ratio=ratio,
                shortfall_kwh=norm_kwh - day.energy_kwh,
                likely_cause=cause,
                cause_detail=detail,
            )
        )
    return sorted(found, key=lambda a: a.day, reverse=True)
