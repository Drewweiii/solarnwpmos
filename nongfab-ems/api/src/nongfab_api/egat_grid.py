"""EGAT national-grid context: what the whole Thai power system is doing right
now, next to what this one 429 kWp site is doing (2026-07-25).

Why this exists. Every number on this dashboard so far describes Nong Fab in
isolation, which makes one question unanswerable: *does rooftop solar here
actually help the country's power system?* The honest answer at this latitude
is "not at the moment that matters", and it takes real national data to show it
rather than assert it - Thailand's system peak lands in the EVENING (2026's
peak was 20:50), hours after any panel has stopped producing. That is a real,
citable finding about solar in Thailand, and it needs EGAT's own numbers.

Source: EGAT SysGen (https://www.sothailand.com/sysgen/), EGAT's public
plan-vs-actual system generation feed - the same data behind their public
realtime page. Key-less JSON, three endpoints:
  - `/api/hist/actual`  today's ACTUAL system generation
  - `/api/control/plan` today's PLANNED curve (what EGAT scheduled)
  - `/api/control/peak` peak records: this year / last year / all time

Thailand-first (see CLAUDE.md): this is a Thai source describing the Thai grid,
so no non-Thailand substitution question arises.

Compliance. `sothailand.com/robots.txt` states no directives at all (its body
is literally "..."), so nothing here is disallowed; requests still carry an
identifying User-Agent and are cached (`MIN_REFRESH_SECONDS`) so a page refresh
never turns into a request per viewer. The upstream itself only updates once a
minute, so polling faster would buy nothing anyway.

TIME IS ICT, NOT UTC. Each series point is `[seconds_since_local_midnight, MW,
ambient_C]` against a `DD-MM-YYYY` day, and both are Asia/Bangkok - verified
empirically when this was written (a sample at 46,920 s appeared while the
Bangkok clock read 13:02). Everything below therefore builds tz-aware ICT
timestamps directly; there is no UTC in this feed to convert from.

Like the other external sources here, the network side can't be exercised from
the egress-blocked CI sandbox - the parsers are unit-tested against captured
response shapes so the wiring is verified offline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

SOURCE_NAME = "egat-sysgen"
BASE_URL = "https://www.sothailand.com/sysgen"
ACTUAL_URL = f"{BASE_URL}/api/hist/actual"
PLAN_URL = f"{BASE_URL}/api/control/plan"
PEAK_URL = f"{BASE_URL}/api/control/peak"

USER_AGENT = "NongFabEMS/1.0 (PTT LNG Nong Fab solar dashboard; research use)"
REQUEST_TIMEOUT_SECONDS = 20.0

# The upstream publishes one new sample per minute; re-fetching more often than
# this only adds load without adding data.
MIN_REFRESH_SECONDS = 60.0

# Asia/Bangkok. Fixed offset rather than a tzdata lookup on purpose: Thailand
# has had no DST and no offset change since 1940, so UTC+7 is exact, and this
# keeps the module free of a zoneinfo dependency in the parse path.
ICT = timezone(timedelta(hours=7), "ICT")


@dataclass(frozen=True)
class GridPoint:
    """One sample of national system generation."""

    at: datetime  # tz-aware ICT
    mw: float
    ambient_c: float | None = None


@dataclass(frozen=True)
class PeakRecord:
    """One all-time/annual system peak, as EGAT reports it."""

    mw: float
    at: datetime | None  # tz-aware ICT; None when the date/time was unparseable
    ambient_c: float | None
    label: str


@dataclass(frozen=True)
class GridSnapshot:
    """Everything the panel needs for one reading of the national system."""

    day: str  # ISO date (ICT)
    actual: list[GridPoint]
    plan: list[GridPoint]
    peaks: list[PeakRecord]


def _parse_day(day: str) -> datetime | None:
    """EGAT's `DD-MM-YYYY` day label -> ICT midnight. None if malformed, so a
    changed upstream format degrades to "no data" rather than to a wrong day."""
    try:
        d = datetime.strptime(day.strip(), "%d-%m-%Y")
    except (ValueError, AttributeError):
        return None
    return d.replace(tzinfo=ICT)


def parse_series(payload: object) -> tuple[str | None, list[GridPoint]]:
    """`{"day": "25-07-2026", "list": [[secs, mw, ambient?], ...]}` -> points.

    Rows are `[seconds_since_ICT_midnight, MW]` with an optional third ambient
    temperature (the plan endpoint omits it). Malformed rows are skipped rather
    than defaulted: a missing MW is not zero MW, and a zero on a national demand
    curve would read as a blackout.
    """
    if not isinstance(payload, dict):
        return None, []
    midnight = _parse_day(payload.get("day", ""))
    rows = payload.get("list")
    if midnight is None or not isinstance(rows, list):
        return None, []

    points: list[GridPoint] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            seconds = float(row[0])
            mw = float(row[1])
        except (TypeError, ValueError):
            continue
        ambient: float | None = None
        if len(row) >= 3:
            try:
                ambient = float(row[2])
            except (TypeError, ValueError):
                ambient = None
        points.append(GridPoint(at=midnight + timedelta(seconds=seconds), mw=mw, ambient_c=ambient))

    points.sort(key=lambda p: p.at)
    return midnight.date().isoformat(), points


_PEAK_LABELS = {
    "thisYear": "สูงสุดปีนี้",
    "lastYear": "สูงสุดปีที่แล้ว",
    "allTime": "สูงสุดตลอดกาล",
}


def parse_peaks(payload: object) -> list[PeakRecord]:
    """`{"thisYear": {...}, "lastYear": {...}, "allTime": {...}}` -> records.

    Each entry carries `value` (MW), `date` (`DD-MM-YYYY`) and `time` (`HH:MM`).
    A record whose timestamp won't parse is still returned with `at=None` - the
    MW figure is the point, and dropping it because the clock string changed
    would lose real information.
    """
    if not isinstance(payload, dict):
        return []
    records: list[PeakRecord] = []
    for key, label in _PEAK_LABELS.items():
        entry = payload.get(key)
        if not isinstance(entry, dict):
            continue
        try:
            mw = float(entry["value"])
        except (KeyError, TypeError, ValueError):
            continue
        records.append(
            PeakRecord(mw=mw, at=_parse_peak_time(entry), ambient_c=_opt_float(entry.get("temperature")), label=label)
        )
    return records


def _parse_peak_time(entry: dict) -> datetime | None:
    day = _parse_day(entry.get("date", ""))
    if day is None:
        return None
    raw = entry.get("time")
    if not isinstance(raw, str):
        return day
    try:
        hh, mm = (int(part) for part in raw.strip().split(":")[:2])
    except (TypeError, ValueError):
        return day
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return day
    return day + timedelta(hours=hh, minutes=mm)


def _opt_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# --- Derived context ---------------------------------------------------------
#
# The point of pulling national data is the comparison, not the curve. These are
# pure so they can be tested without touching the network.


def series_peak(points: list[GridPoint]) -> GridPoint | None:
    """The highest sample in a series - today's system peak so far. Note "so
    far": before evening this is a running maximum, not the day's peak, which is
    exactly why the response labels it that way rather than as "today's peak"."""
    return max(points, key=lambda p: p.mw) if points else None


def value_at(points: list[GridPoint], when: datetime) -> GridPoint | None:
    """The sample nearest `when`, or None for an empty series. Nearest rather
    than interpolated: these are 1-minute samples of a slow-moving national
    curve, so the closest reading is the honest answer and inventing a value
    between two real ones adds nothing."""
    if not points:
        return None
    return min(points, key=lambda p: abs((p.at - when).total_seconds()))


def plan_deviation_mw(actual: list[GridPoint], plan: list[GridPoint]) -> float | None:
    """Actual minus planned at the newest actual sample: positive = the country
    is drawing MORE than EGAT scheduled. None when either side is empty."""
    if not actual or not plan:
        return None
    latest = actual[-1]
    planned = value_at(plan, latest.at)
    return None if planned is None else latest.mw - planned.mw


def share_of_system_pct(site_kw: float, system_mw: float) -> float | None:
    """This site's output as a percentage of national generation. None on a
    non-positive system figure rather than a divide-by-zero."""
    if system_mw <= 0:
        return None
    return (site_kw / 1000.0) / system_mw * 100.0


def peak_is_after_sunset(peak_at: datetime | None, sunset: datetime | None) -> bool | None:
    """Whether the system peak lands after the sun is down - the finding this
    whole panel exists to make visible. None when either time is unknown, so an
    unparseable upstream timestamp never becomes a confident 'no'."""
    if peak_at is None or sunset is None:
        return None
    return peak_at.timetz() > sunset.timetz()


async def fetch_snapshot(client: httpx.AsyncClient | None = None) -> GridSnapshot | None:
    """Pull all three endpoints. Returns None when the actual series - the one
    thing the panel cannot be drawn without - is unavailable; the plan and peak
    endpoints degrade to empty independently, so one of them failing still
    leaves a usable reading rather than an empty panel.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
    try:
        actual_payload = await _get_json(client, ACTUAL_URL)
        day, actual = parse_series(actual_payload)
        if day is None or not actual:
            logger.warning("%s: no usable actual series", SOURCE_NAME)
            return None
        _, plan = parse_series(await _get_json(client, PLAN_URL))
        peaks = parse_peaks(await _get_json(client, PEAK_URL))
        return GridSnapshot(day=day, actual=actual, plan=plan, peaks=peaks)
    finally:
        if owns_client:
            await client.aclose()


async def _get_json(client: httpx.AsyncClient, url: str) -> object:
    """One GET, JSON-decoded. Any failure returns None so a single dead endpoint
    can't take the whole snapshot down with it."""
    try:
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001 - any upstream problem is "no data"
        logger.warning("%s: %s failed (%s)", SOURCE_NAME, url, exc)
        return None
