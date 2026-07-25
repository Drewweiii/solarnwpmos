"""Hour-of-day carbon intensity of the Thai grid, and what it means for a solar
array that only ever produces in the middle of the day (2026-07-25).

Why this exists. The Energy Report values every avoided kWh at ONE annual grid
emission factor (`green.ef_scope2_kg_per_kwh`, กกพ's 0.4758). That is the
correct convention for reporting, but it is physically wrong in an interesting
way: at 02:00 the Thai system is running on its cheapest baseload plant, and at
14:00 - exactly when this array produces - it is running that baseload PLUS
whatever expensive, usually dirtier unit was needed to meet the extra demand.
A flat factor cannot see that difference, so it cannot answer "does solar here
displace clean electricity or dirty electricity?"

WHAT IS REAL HERE AND WHAT IS MODELLED - read this before quoting any number.

  REAL   The load curve. EGAT SysGen's per-minute national generation (see
         `egat_grid.py`), which is measured, public, and Thai.
  REAL   The published annual emission factor the whole thing is calibrated
         to. The model is *forced* to reproduce it (see `calibrate`), so this
         module can never quietly publish a different headline number than the
         Energy Report does.
  CITED  Per-fuel emission factors: IPCC AR5 WG3 Annex III lifecycle medians
         (gCO2eq/kWh). Literature values, not measurements of Thai plant.
  MODEL  Which fuel is on the margin at a given load. Thailand does not publish
         real-time generation by fuel type - EPPO and EGAT publish it monthly,
         in reports, after the fact - so the split across the day is inferred
         from a merit-order stack against the day's own load-duration curve.
  PLACEHOLDER  The fuel mix shares themselves. `DEFAULT_MIX` below is an
         approximation, NOT a figure taken from an EPPO table, and it is
         labelled as such everywhere it surfaces. Replace it with EPPO's real
         monthly generation-by-fuel numbers; the shares are editable settings
         (`gridmix.*`) precisely so that can happen without a code change.

So: the LEVEL of this curve is real (calibrated to กกพ), its SHAPE is a model,
and the mix driving the shape is a placeholder awaiting real monthly data. The
API response carries those labels so a viewer sees them too.

The method. Stack the fuels in merit order (cheapest dispatched first) as
horizontal bands under the day's load-duration curve, sized so each band's area
equals that fuel's share of the day's energy. At any instant the system load
sits inside exactly one band: that band's fuel is the MARGINAL fuel - the one
that would burn less if this array produced one more kWh right then. Everything
below it is the mix actually running, whose energy-weighted factor is the
AVERAGE intensity at that moment.

Marginal is the honest factor for "what did our solar displace"; average is the
honest factor for "what was the grid's intensity". Both are returned, because
they answer different questions and mixing them up is the classic error in this
kind of analysis.

WHAT THE MODEL ACTUALLY SAYS FOR THAILAND, and it is not what you might expect.
Thai demand never falls far enough overnight for the gas fleet to come off the
margin - the trough is roughly two-thirds of the peak, and gas alone is around
60% of generation - so the marginal fuel comes out as NATURAL GAS at every hour
of the day. The marginal curve is therefore nearly flat, which looks like a bug
and is not: it is the finding. Every kWh this array makes displaces gas at
roughly 0.49 kgCO2eq/kWh, not the 0.4758 grid-average the Energy Report credits
it with, so the flat annual factor slightly UNDERSTATES the site. The average
curve does still vary across the day, because more of the gas band is in use at
the peak than at the trough.

That also means the interesting variation would only appear in a system with a
distinct peaking fuel above gas. `oil` is in the merit order for exactly that
reason, at a share of zero by default.

Thailand-first (CLAUDE.md): load data is EGAT's own, the calibration target is
กกพ's own, timestamps are ICT. The only non-Thai input is the IPCC per-fuel
factor table, which is a global reference standard rather than another
country's data standing in for Thailand's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .egat_grid import GridPoint

# --- Per-fuel emission factors ----------------------------------------------
#
# IPCC AR5 WG3 Annex III, lifecycle medians in gCO2eq/kWh. Lifecycle rather than
# combustion-only so that "zero-carbon" sources are not modelled as literally
# zero - hydro and solar are small, not nil.
#
# Two deliberate simplifications, both stated rather than hidden:
#  * coal and lignite share IPCC's coal median (820). Thai lignite is dirtier
#    than that; treating it as ordinary coal UNDERSTATES the grid's intensity
#    at the moment lignite is marginal.
#  * `renewables` uses the utility solar PV median (48) even though Thailand's
#    renewable generation is substantially biomass (IPCC median 230). This too
#    understates the grid factor.
# Both errors push the same way - they make this array look LESS beneficial,
# not more - which is the safe direction for a figure that will be published.
IPCC_AR5_G_PER_KWH: dict[str, float] = {
    "oil": 650.0,  # not an AR5 headline row; commonly cited range 650-780
    "natural_gas": 490.0,
    "coal_lignite": 820.0,
    "renewables": 48.0,
    "imported": 24.0,  # predominantly Lao hydro under long-term PPA
    "hydro": 24.0,
}


@dataclass(frozen=True)
class Fuel:
    """One dispatchable category, with where it sits in the merit order.

    `merit_rank` ascends with marginal cost: rank 0 is dispatched first and is
    therefore never the marginal unit unless the system is running on almost
    nothing. Oil/diesel sits at the top because in Thailand it is peaking plant.
    """

    key: str
    label: str
    ef_kg_per_kwh: float
    merit_rank: int


# Ordered cheapest-first. Domestic hydro is modelled as must-run alongside the
# imports, which is the first-order approximation: reservoir hydro is in truth
# partly peaking, so at the evening peak this model attributes to gas some
# generation that is really hydro. That is a known limitation of the shape, not
# of the level (which is pinned by calibration).
FUELS: tuple[Fuel, ...] = (
    Fuel("renewables", "พลังงานหมุนเวียน", IPCC_AR5_G_PER_KWH["renewables"] / 1000.0, 0),
    Fuel("hydro", "พลังน้ำในประเทศ", IPCC_AR5_G_PER_KWH["hydro"] / 1000.0, 1),
    Fuel("imported", "นำเข้า (ส่วนใหญ่พลังน้ำ สปป.ลาว)", IPCC_AR5_G_PER_KWH["imported"] / 1000.0, 2),
    Fuel("coal_lignite", "ถ่านหิน/ลิกไนต์", IPCC_AR5_G_PER_KWH["coal_lignite"] / 1000.0, 3),
    Fuel("natural_gas", "ก๊าซธรรมชาติ", IPCC_AR5_G_PER_KWH["natural_gas"] / 1000.0, 4),
    Fuel("oil", "น้ำมัน/ดีเซล (เดินเครื่องช่วงพีค)", IPCC_AR5_G_PER_KWH["oil"] / 1000.0, 5),
)

BY_KEY: dict[str, Fuel] = {f.key: f for f in FUELS}

# PLACEHOLDER, not an EPPO figure. Shares of national ELECTRICITY GENERATION,
# in the ballpark of Thailand's published annual mix but never reconciled
# against a specific EPPO monthly table. Every surface that shows a number
# derived from these must say so; `MIX_ORIGIN_PLACEHOLDER` is what carries that
# label through the API.
DEFAULT_MIX: dict[str, float] = {
    "natural_gas": 0.60,
    "coal_lignite": 0.16,
    "imported": 0.14,
    "renewables": 0.09,
    "hydro": 0.01,
    "oil": 0.00,
}

MIX_ORIGIN_PLACEHOLDER = "placeholder"
MIX_ORIGIN_PUBLISHED = "published"

MIX_PLACEHOLDER_NOTE = (
    "สัดส่วนเชื้อเพลิงชุดนี้เป็นค่าประมาณ ยังไม่ได้ยืนยันกับตารางรายเดือนของ EPPO/กฟผ. "
    "รูปร่างของกราฟจึงเป็นแบบจำลอง ส่วนระดับค่าเฉลี่ยถูกตรึงไว้กับ GEF ที่เผยแพร่จริง"
)


def normalised_shares(shares: dict[str, float]) -> dict[str, float]:
    """Drop unknown/negative entries and rescale what is left to sum to 1.

    Rescaling rather than rejecting: a mix that sums to 0.98 because of rounding
    in a published table is a usable mix, and refusing it would make the panel
    disappear over a rounding error. An empty or all-zero mix returns {} so
    callers can show "no data" instead of dividing by zero.
    """
    clean = {k: float(v) for k, v in shares.items() if k in BY_KEY and float(v) > 0.0}
    total = sum(clean.values())
    if total <= 0.0:
        return {}
    return {k: v / total for k, v in clean.items()}


@dataclass(frozen=True)
class Band:
    """One fuel's horizontal slab of the load-duration curve, in MW.

    `top_mw` is the load level at which this fuel stops being marginal and the
    next one up takes over.
    """

    fuel: Fuel
    bottom_mw: float
    top_mw: float


def _energy_between(loads: list[float], bottom: float, top: float) -> float:
    """Area of the load-duration curve between two horizontal levels.

    Equal sample spacing is assumed, so "area" is just a sum - EGAT's feed is
    uniformly one sample per minute, and using the sample count keeps this
    independent of what that interval happens to be.
    """
    if top <= bottom:
        return 0.0
    return sum(min(load, top) - min(load, bottom) for load in loads)


def build_bands(loads: list[float], shares: dict[str, float]) -> list[Band]:
    """Slice the load-duration curve into one horizontal band per fuel.

    Each band is sized so its area equals that fuel's share of the day's total
    energy, filling from the bottom in merit order. Solved by bisection on the
    band's top edge because the area is a monotone but piecewise-linear function
    of that edge - there is no closed form once the curve has real structure.
    """
    usable = normalised_shares(shares)
    if not usable or not loads:
        return []

    total_energy = sum(loads)
    if total_energy <= 0.0:
        return []

    ceiling = max(loads)
    bands: list[Band] = []
    bottom = 0.0
    ordered = sorted((BY_KEY[k] for k in usable), key=lambda f: f.merit_rank)

    for index, fuel in enumerate(ordered):
        if index == len(ordered) - 1:
            # The top fuel takes whatever is left, exactly. Solving for it too
            # would leave a sliver of unassigned area from accumulated
            # bisection error, and an unassigned sliver at the very top is
            # precisely where the marginal fuel is read from.
            bands.append(Band(fuel=fuel, bottom_mw=bottom, top_mw=ceiling))
            break

        target = usable[fuel.key] * total_energy
        lo, hi = bottom, ceiling
        for _ in range(60):  # ~1e-18 relative; converges long before that
            mid = (lo + hi) / 2.0
            if _energy_between(loads, bottom, mid) < target:
                lo = mid
            else:
                hi = mid
        top = (lo + hi) / 2.0
        bands.append(Band(fuel=fuel, bottom_mw=bottom, top_mw=top))
        bottom = top

    return bands


def marginal_fuel(bands: list[Band], load_mw: float) -> Fuel | None:
    """The fuel whose band contains this load - the unit that would back off if
    the site produced one more kWh at this instant. None when there are no
    bands; loads above the top band clamp to the top fuel, since a load above
    the day's own maximum can only come from a later, higher sample."""
    if not bands:
        return None
    for band in bands:
        if load_mw <= band.top_mw:
            return band.fuel
    return bands[-1].fuel


def average_ef_kg_per_kwh(bands: list[Band], load_mw: float) -> float | None:
    """Energy-weighted factor of everything running at this load.

    Every band fully below the load contributes its whole width; the band the
    load sits in contributes only the part below the load. That is what makes
    this fall between the cleanest and dirtiest fuel rather than jumping.
    """
    if not bands or load_mw <= 0.0:
        return None
    weighted = 0.0
    covered = 0.0
    for band in bands:
        width = min(load_mw, band.top_mw) - min(load_mw, band.bottom_mw)
        if width <= 0.0:
            continue
        weighted += width * band.fuel.ef_kg_per_kwh
        covered += width
    if covered <= 0.0:
        return None
    return weighted / covered


def calibrate(loads: list[float], bands: list[Band], published_ef: float) -> float:
    """Scale factor that forces the model's energy-weighted mean onto the
    published annual GEF.

    This is the guardrail that keeps the module honest. Without it, a
    placeholder mix and a global EF table would together produce some *other*
    average intensity for Thailand, and the site would be publishing two
    different national carbon figures on two different pages. With it, the
    modelled curve is a redistribution of the official number across the day -
    it can say "midday is above average", never "the average is different".

    Returns 1.0 when it cannot be computed, so an uncalibratable curve is
    shown unscaled rather than suppressed.
    """
    if not loads or not bands or published_ef <= 0.0:
        return 1.0
    weighted = 0.0
    total = 0.0
    for load in loads:
        ef = average_ef_kg_per_kwh(bands, load)
        if ef is None:
            continue
        weighted += ef * load
        total += load
    if total <= 0.0 or weighted <= 0.0:
        return 1.0
    return published_ef / (weighted / total)


@dataclass(frozen=True)
class CarbonPoint:
    """Grid carbon intensity at one instant."""

    at: datetime
    load_mw: float
    average_kg_per_kwh: float
    marginal_kg_per_kwh: float
    marginal_fuel_key: str
    marginal_fuel_label: str


def carbon_curve(
    points: list[GridPoint],
    shares: dict[str, float],
    published_ef: float,
) -> list[CarbonPoint]:
    """The day's carbon intensity, instant by instant, calibrated to `published_ef`.

    Bands are built once from the whole day, not per point: the merit order is a
    property of the day's dispatch, and rebuilding it per sample would make each
    instant its own little grid.
    """
    loads = [p.mw for p in points if p.mw > 0.0]
    bands = build_bands(loads, shares)
    if not bands:
        return []
    scale = calibrate(loads, bands, published_ef)

    curve: list[CarbonPoint] = []
    for point in points:
        if point.mw <= 0.0:
            continue
        average = average_ef_kg_per_kwh(bands, point.mw)
        fuel = marginal_fuel(bands, point.mw)
        if average is None or fuel is None:
            continue
        curve.append(
            CarbonPoint(
                at=point.at,
                load_mw=point.mw,
                average_kg_per_kwh=average * scale,
                marginal_kg_per_kwh=fuel.ef_kg_per_kwh * scale,
                marginal_fuel_key=fuel.key,
                marginal_fuel_label=fuel.label,
            )
        )
    return curve


def hourly_means(curve: list[CarbonPoint]) -> list[dict[str, object]]:
    """Collapse the per-minute curve to 24 ICT hours.

    The panel plots hours, and shipping 1,440 points so the browser can average
    them itself would be wasteful. Hours with no samples are omitted rather than
    zero-filled - the feed only carries the day so far, and a zero at 23:00
    would read as "the grid is carbon-free tonight".
    """
    buckets: dict[int, list[CarbonPoint]] = {}
    for point in curve:
        buckets.setdefault(point.at.hour, []).append(point)

    rows: list[dict[str, object]] = []
    for hour in sorted(buckets):
        group = buckets[hour]
        marginal_keys = [p.marginal_fuel_key for p in group]
        dominant = max(set(marginal_keys), key=marginal_keys.count)
        rows.append(
            {
                "hour": hour,
                "load_mw": sum(p.load_mw for p in group) / len(group),
                "average_kg_per_kwh": sum(p.average_kg_per_kwh for p in group) / len(group),
                "marginal_kg_per_kwh": sum(p.marginal_kg_per_kwh for p in group) / len(group),
                "marginal_fuel_key": dominant,
                "marginal_fuel_label": BY_KEY[dominant].label,
                "samples": len(group),
            }
        )
    return rows


def solar_weighted_ef(
    hours: list[dict[str, object]],
    generation_by_hour: dict[int, float],
    field: str = "marginal_kg_per_kwh",
) -> float | None:
    """The emission factor this array actually earns, weighted by WHEN it produces.

    This is the payoff of the whole module: compare it against the flat annual
    factor and the difference is the part of the site's carbon benefit that a
    flat factor cannot see. None when the two series do not overlap, rather than
    a number computed from one hour that happened to line up.
    """
    weighted = 0.0
    total = 0.0
    for row in hours:
        kwh = generation_by_hour.get(int(row["hour"]), 0.0)  # type: ignore[arg-type]
        if kwh <= 0.0:
            continue
        weighted += float(row[field]) * kwh  # type: ignore[arg-type]
        total += kwh
    if total <= 0.0:
        return None
    return weighted / total
