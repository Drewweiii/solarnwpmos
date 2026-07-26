"""How did the forecast for a given hour change as that hour approached?
(2026-07-25, project D)

A forecast is not one number, it is a sequence of answers to the same question,
each issued closer to the event than the last. The dashboard has only ever shown
the newest answer. That hides the thing an operator actually learns to trust or
distrust a model by: whether its story converges as the hour nears, or lurches.

A forecast that reads 180 kW three days out, 175 kW yesterday and 172 kW this
morning is a model that knew what it was talking about early. One that reads
180, then 90, then 165 is not - even if the last number turns out to be right.
Both look identical on a chart that shows only the latest issuance.

WHY A SEPARATE TABLE EXISTS FOR THIS. `forecast_history` keys on
(zone, horizon, target_time) and replaces on write - by design, because serving
a chart wants the best available forecast for each hour, and a superseded
issuance is strictly worse for that purpose. The consequence is that the earlier
answers were destroyed the moment a better one arrived, so this question could
not be asked of that table at all. `forecast_evolution` keeps them; nothing is
ever served from it.

The honest limit, which any surface showing this has to state: the table starts
empty and fills from the moment it was deployed. It cannot show the evolution of
a forecast issued before it existed, and it needs several issuances for one
target hour before a convergence line means anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Fewer issuances than this and a "convergence" line is two dots and a story.
MIN_ISSUANCES_FOR_A_TREND = 3


@dataclass(frozen=True)
class Issuance:
    """One answer, and how far ahead of the event it was given."""

    issued_at: datetime
    lead_hours: float
    pred_kw: float
    lower_kw: float | None = None
    upper_kw: float | None = None


@dataclass(frozen=True)
class TargetEvolution:
    """Every answer the system gave for one target hour, newest last."""

    target_time: datetime
    issuances: list[Issuance]

    @property
    def n(self) -> int:
        return len(self.issuances)

    @property
    def first(self) -> Issuance | None:
        return self.issuances[0] if self.issuances else None

    @property
    def latest(self) -> Issuance | None:
        return self.issuances[-1] if self.issuances else None

    @property
    def total_revision_kw(self) -> float | None:
        """How far the answer moved in total, first issuance to last. The
        headline: signed, because "we were 40 kW too optimistic three days out"
        and "too pessimistic" are different stories."""
        if self.n < 2:
            return None
        return self.issuances[-1].pred_kw - self.issuances[0].pred_kw

    @property
    def max_swing_kw(self) -> float | None:
        """The widest gap between any two answers for this hour.

        Not the same as the total revision, and the difference is the whole
        point: a forecast that went 180 -> 90 -> 175 has a total revision of
        -5 kW, which reads as a model that barely changed its mind. Its swing
        is 90 kW, which is what actually happened.
        """
        if self.n < 2:
            return None
        values = [i.pred_kw for i in self.issuances]
        return max(values) - min(values)

    def is_converging(self, tolerance_kw: float = 0.0) -> bool | None:
        """Whether successive revisions got smaller as the hour approached.

        None below `MIN_ISSUANCES_FOR_A_TREND`: with two answers there is one
        revision and nothing to compare it to, and calling that "converging"
        would be a verdict drawn from a single data point.
        """
        if self.n < MIN_ISSUANCES_FOR_A_TREND:
            return None
        revisions = [
            abs(b.pred_kw - a.pred_kw) for a, b in zip(self.issuances, self.issuances[1:])
        ]
        # Compare the second half of the revisions with the first: a strict
        # "every step smaller than the last" test would call one noisy hop a
        # failure to converge, which is too brittle to be useful.
        midpoint = len(revisions) // 2 or 1
        early = revisions[:midpoint]
        late = revisions[midpoint:] or revisions[-1:]
        return (sum(late) / len(late)) <= (sum(early) / len(early)) + tolerance_kw


def build_evolution(rows: list[tuple], target_time: datetime) -> TargetEvolution:
    """Assemble one target hour's issuances from stored rows.

    `rows` are `(target_time, issued_at, pred, lower, upper)` as
    `RealDataStore.forecast_evolution_rows` returns them, already parsed to
    datetimes; rows for other target hours are ignored so a caller can pass the
    whole window.

    Issuances after the target hour are dropped: a row issued at or past the
    event is not a forecast of it, and including one would show the line
    "converging" onto an answer given after the fact.
    """
    issuances: list[Issuance] = []
    for row in rows:
        row_target, issued_at, pred = row[0], row[1], float(row[2])
        if row_target != target_time:
            continue
        lead_hours = (target_time - issued_at).total_seconds() / 3600.0
        if lead_hours <= 0:
            continue
        issuances.append(
            Issuance(
                issued_at=issued_at,
                lead_hours=lead_hours,
                pred_kw=pred,
                lower_kw=None if len(row) < 4 or row[3] is None else float(row[3]),
                upper_kw=None if len(row) < 5 or row[4] is None else float(row[4]),
            )
        )
    # Oldest issuance first, so "first" means the earliest answer given.
    issuances.sort(key=lambda i: i.issued_at)
    return TargetEvolution(target_time=target_time, issuances=issuances)


def most_revised_target(
    rows: list[tuple], min_issuances: int = MIN_ISSUANCES_FOR_A_TREND
) -> TargetEvolution | None:
    """The target hour whose forecast moved the most, among those with enough
    issuances to be worth showing.

    Chosen by SWING rather than by total revision, for the reason
    `max_swing_kw` documents: an hour the model changed its mind about twice and
    came back from is the interesting one, and total revision scores it as
    boring.
    """
    targets = {row[0] for row in rows}
    best: TargetEvolution | None = None
    best_swing = -1.0
    for target in targets:
        evolution = build_evolution(rows, target)
        if evolution.n < min_issuances:
            continue
        swing = evolution.max_swing_kw or 0.0
        if swing > best_swing:
            best, best_swing = evolution, swing
    return best
