"""How fast is the output about to change? (2026-07-25, project B)

Every forecast surface in this system answers "how much" and none of them
answers "how fast". Those are different questions, and for a solar plant the
second one is the one that arrives suddenly: a cloud front crossing the array
takes output from near-nameplate to a fraction of it inside an hour, and a
level forecast that is perfectly accurate at both ends still never says that a
cliff sits between them.

Ramp forecasting is a standard product in operational solar forecasting for that
reason. This module produces it from the forecast series the system already
issues - no new model, no new data.

WHAT THIS IS FOR AT THIS SITE, HONESTLY. Nong Fab is fully grid-tied with no
battery and no curtailment control (see the root CLAUDE.md note on why the
project pivoted toward investment questions in the first place). So a ramp
warning here does NOT trigger a dispatch decision - there is nothing to
dispatch. It is information: it tells whoever is watching that a swing is
coming and roughly how big, and it makes the array's variability visible as a
measured quantity instead of an impression. Any surface showing these numbers
has to say that, rather than implying an operator is expected to act.

Severity is expressed as a percentage of the zone's AC capacity per hour, not in
raw kW, so the same threshold means the same thing on GIS (50 kW) and Jetty
(200 kW), and so a reader can compare zones without doing arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Severity bands, as a fraction of AC capacity per hour. Conventions chosen for
# this project, not measurements: they exist so a table can be read at a glance,
# and they are exposed as settings so the line can be moved.
DEFAULT_MODERATE_FRACTION = 0.20
DEFAULT_STEEP_FRACTION = 0.40

SEVERITY_CALM = "calm"
SEVERITY_MODERATE = "moderate"
SEVERITY_STEEP = "steep"

DIRECTION_UP = "up"
DIRECTION_DOWN = "down"
DIRECTION_FLAT = "flat"

# Below this the change is not a ramp in any useful sense - it is the model
# breathing. As a fraction of capacity per hour.
FLAT_FRACTION = 0.02


@dataclass(frozen=True)
class Ramp:
    """One step-to-step change in forecast output."""

    from_time: datetime
    to_time: datetime
    from_kw: float
    to_kw: float
    hours: float

    @property
    def delta_kw(self) -> float:
        return self.to_kw - self.from_kw

    @property
    def rate_kw_per_h(self) -> float:
        """Signed rate. Division by `hours` matters: a 30 kW change over three
        hours and the same change over one are the same delta and very different
        events, and only the rate tells them apart."""
        return self.delta_kw / self.hours if self.hours > 0 else 0.0

    def pct_of_capacity_per_h(self, capacity_kw: float | None) -> float | None:
        if not capacity_kw or capacity_kw <= 0:
            return None
        return 100.0 * self.rate_kw_per_h / capacity_kw

    def direction(self, capacity_kw: float | None, flat_fraction: float = FLAT_FRACTION) -> str:
        pct = self.pct_of_capacity_per_h(capacity_kw)
        if pct is None:
            # No capacity to normalise against: fall back to the raw sign rather
            # than calling everything flat.
            if self.rate_kw_per_h > 0:
                return DIRECTION_UP
            return DIRECTION_DOWN if self.rate_kw_per_h < 0 else DIRECTION_FLAT
        if abs(pct) < flat_fraction * 100.0:
            return DIRECTION_FLAT
        return DIRECTION_UP if pct > 0 else DIRECTION_DOWN

    def severity(
        self,
        capacity_kw: float | None,
        moderate_fraction: float = DEFAULT_MODERATE_FRACTION,
        steep_fraction: float = DEFAULT_STEEP_FRACTION,
    ) -> str:
        """Severity of the magnitude, direction ignored - a 40%/h climb is as
        much of a swing as a 40%/h collapse, and the direction is reported
        separately so a reader can care about one and not the other."""
        pct = self.pct_of_capacity_per_h(capacity_kw)
        if pct is None:
            return SEVERITY_CALM
        magnitude = abs(pct) / 100.0
        if magnitude >= steep_fraction:
            return SEVERITY_STEEP
        if magnitude >= moderate_fraction:
            return SEVERITY_MODERATE
        return SEVERITY_CALM


def ramps_from_series(series: list[tuple[datetime, float]]) -> list[Ramp]:
    """Consecutive-step ramps from a (time, kW) series.

    The series is sorted first and duplicate timestamps are collapsed to the
    last value seen: the forecast store can hold more than one row for an hour
    across issuances, and a duplicate would otherwise produce a phantom ramp of
    zero duration between two readings of the same hour.
    """
    if len(series) < 2:
        return []
    collapsed: dict[datetime, float] = {}
    for when, value in series:
        collapsed[when] = float(value)
    ordered = sorted(collapsed.items())

    ramps: list[Ramp] = []
    for (t0, v0), (t1, v1) in zip(ordered, ordered[1:]):
        hours = (t1 - t0).total_seconds() / 3600.0
        if hours <= 0:
            continue
        ramps.append(Ramp(from_time=t0, to_time=t1, from_kw=v0, to_kw=v1, hours=hours))
    return ramps


def steepest_down_ramp(
    ramps: list[Ramp],
    capacity_kw: float | None,
    moderate_fraction: float = DEFAULT_MODERATE_FRACTION,
    steep_fraction: float = DEFAULT_STEEP_FRACTION,
) -> Ramp | None:
    """The sharpest fall in the window, or None when nothing qualifies.

    Only ramps that reach at least the moderate band are eligible. Returning the
    least-shallow of a set of non-events would put a warning on screen for
    ordinary afternoon drift, and a warning that fires every day is one nobody
    reads.
    """
    candidates = [
        r
        for r in ramps
        if r.rate_kw_per_h < 0 and r.severity(capacity_kw, moderate_fraction, steep_fraction) != SEVERITY_CALM
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: r.rate_kw_per_h)


@dataclass(frozen=True)
class RampStatistics:
    """How ramp-prone this array has actually been, from recorded history."""

    n_steps: int
    n_moderate_down: int
    n_steep_down: int
    n_moderate_up: int
    n_steep_up: int
    # Largest fall and climb seen, in percent of capacity per hour.
    worst_down_pct_per_h: float | None
    worst_up_pct_per_h: float | None
    # ICT hour of day where significant down-ramps cluster, and how many landed
    # there. None when there were none to cluster.
    busiest_down_hour_ict: int | None
    busiest_down_hour_count: int


EMPTY_STATISTICS = RampStatistics(
    n_steps=0,
    n_moderate_down=0,
    n_steep_down=0,
    n_moderate_up=0,
    n_steep_up=0,
    worst_down_pct_per_h=None,
    worst_up_pct_per_h=None,
    busiest_down_hour_ict=None,
    busiest_down_hour_count=0,
)

# ICT is UTC+7. Hard-coded rather than pulled from a tz database because this is
# arithmetic on an hour number for a histogram bucket, not a timestamp being
# rendered - and Thailand has no daylight saving to complicate it.
ICT_OFFSET_HOURS = 7


def ramp_statistics(
    ramps: list[Ramp],
    capacity_kw: float | None,
    moderate_fraction: float = DEFAULT_MODERATE_FRACTION,
    steep_fraction: float = DEFAULT_STEEP_FRACTION,
) -> RampStatistics:
    """Count and characterise the ramps in a recorded history.

    The point of this half is that it is measured, not forecast: it says how
    often this array has really swung, which is the context that tells a reader
    whether an upcoming ramp warning is routine or unusual.
    """
    if not ramps:
        return EMPTY_STATISTICS

    down_hours: dict[int, int] = {}
    counts = {"moderate_down": 0, "steep_down": 0, "moderate_up": 0, "steep_up": 0}
    worst_down: float | None = None
    worst_up: float | None = None

    for ramp in ramps:
        pct = ramp.pct_of_capacity_per_h(capacity_kw)
        if pct is None:
            continue
        severity = ramp.severity(capacity_kw, moderate_fraction, steep_fraction)
        going_down = ramp.rate_kw_per_h < 0
        if severity != SEVERITY_CALM:
            key = f"{severity}_{'down' if going_down else 'up'}"
            counts[key] = counts.get(key, 0) + 1
            if going_down:
                hour_ict = (ramp.from_time.hour + ICT_OFFSET_HOURS) % 24
                down_hours[hour_ict] = down_hours.get(hour_ict, 0) + 1
        if going_down and (worst_down is None or pct < worst_down):
            worst_down = pct
        if not going_down and (worst_up is None or pct > worst_up):
            worst_up = pct

    busiest_hour = max(down_hours.items(), key=lambda kv: kv[1]) if down_hours else None
    return RampStatistics(
        n_steps=len(ramps),
        n_moderate_down=counts["moderate_down"],
        n_steep_down=counts["steep_down"],
        n_moderate_up=counts["moderate_up"],
        n_steep_up=counts["steep_up"],
        worst_down_pct_per_h=worst_down,
        worst_up_pct_per_h=worst_up,
        busiest_down_hour_ict=busiest_hour[0] if busiest_hour else None,
        busiest_down_hour_count=busiest_hour[1] if busiest_hour else 0,
    )
