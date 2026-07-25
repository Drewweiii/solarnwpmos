"""Is this array pointed the right way? (2026-07-25, roadmap project D)

What this answers. Every zone was built at some tilt and azimuth, and nothing in
this system has ever checked whether those are the angles that actually collect
the most energy at 12.7 N. This sweeps the alternatives against the site's own
sun path and reports the gap - in kWh/year, so it can be priced.

WHY IT NEEDED A NEW IRRADIANCE PATH, which is the finding worth reading.

Until now tilt affected exactly one thing in this codebase: inter-row
self-shading (`features.shading`). The ENERGY model never used it -
`simulate_zone_baseline` is handed `ghi_clearsky`, which is irradiance on a
HORIZONTAL surface, so as far as yield was concerned every panel here might as
well have been lying flat. Asking "what is the best tilt?" of that model would
have returned "it does not matter", which is wrong rather than uninformative.

So this module transposes GHI/DNI/DHI onto the tilted plane (pvlib's Hay-Davies
model) to get plane-of-array irradiance, which is what a tilted panel actually
sees. That makes tilt a real variable.

IMPORTANT - THIS DOES NOT CHANGE ANY PUBLISHED FIGURE. The main pipeline still
runs on GHI, so /financial, /savings and the Energy Report are untouched by this
file. That is deliberate: adopting POA site-wide would move the published annual
yield and therefore the payback, which is the user's call, not a side effect of
adding an advisory panel. The comparison below is internally consistent because
BOTH sides of it - as-built and candidate - use the same POA model.

AND THE LIMIT THAT DECIDES WHAT MAY BE CLAIMED. config/assets.yaml has
`tilt_deg: null` for every zone - "not measured - SLD is electrical-only; looks
ground-mount from photos". So the array's real angle is UNKNOWN, and the
"current" side of every comparison here is `panel_geometry`'s assumed default.
That makes "you are losing N kWh/year" unsayable about the built array, and
`current_is_measured` carries that fact through to the API and the screen.

The optimum is unaffected: it depends on the sun path, not on what was built,
so it stands on its own - and it is exactly what the expansion phases, which do
not exist yet, should be designed to.

Scope, stated rather than implied:
  * Clear-sky irradiance over 12 mid-month representative days, weighted by
    real month lengths - the same sampling `monthly_ac_energy_estimates` uses,
    so the seasonal shape is genuine astronomy at Nong Fab's coordinates.
    Clouds are not modelled; they scale both orientations similarly, so they
    move the absolute kWh but barely move which angle wins.
  * Monofacial. These are bifacial modules, and rear-side gain depends on
    ground albedo and mounting height that were never surveyed here.
  * ROW PITCH IS HELD AT AS-BUILT. Widening pitch cuts self-shading, but this
    site's land is capped, so a wider pitch means fewer rows and less installed
    capacity - trading a loss for a smaller array is not a like-for-like
    comparison, and doing it honestly needs a land-area constraint this module
    does not have. Pitch optimisation is therefore left out rather than done
    misleadingly.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone as dt_timezone
from functools import lru_cache

import numpy as np
import pandas as pd
import pvlib
from nongfab_common.assets import load_assets
from nongfab_features.clearsky import compute_clearsky_and_position, nong_fab_site_location
from nongfab_features.panel_geometry import generate_zone_layout
from nongfab_features.shading import row_shaded_fraction

from .pipeline import NONG_FAB_TZ

# Ground reflectance for the ground-reflected term. pvlib's own default, and a
# standard value for mixed industrial ground - not a site measurement. It moves
# all orientations in the same direction, so it barely affects which one wins.
DEFAULT_ALBEDO = 0.25

# Sweep resolution. 1 degree in tilt is far finer than anyone can mount to, but
# the sweep is cheap and a coarse grid can miss a shallow optimum's true centre.
TILT_STEP_DEG = 1.0
AZIMUTH_STEP_DEG = 5.0


@dataclass(frozen=True)
class OrientationYield:
    """One candidate orientation and what it would collect."""

    tilt_deg: float
    azimuth_deg: float
    # Annual plane-of-array irradiance before self-shading.
    poa_kwh_per_m2: float
    # Clear-sky-energy-weighted inter-row shading loss at this geometry.
    shading_loss_pct: float

    @property
    def effective_kwh_per_m2(self) -> float:
        """What the array actually collects: POA minus what the row in front
        takes. This - not raw POA - is what the optimum must be chosen on,
        because tilting further up gains POA and loses it again to shading."""
        return self.poa_kwh_per_m2 * (1.0 - self.shading_loss_pct / 100.0)


def _representative_index(year: int) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """12 mid-month days at hourly resolution, plus each sample's month length.

    Mid-month days rather than a full 8760 because the sun path is smooth: 288
    samples reproduce the annual total to well under a percent while keeping a
    full tilt x azimuth sweep interactive.
    """
    frames = []
    weights = []
    for month in range(1, 13):
        start = pd.Timestamp(year=year, month=month, day=15, tz=NONG_FAB_TZ)
        idx = pd.date_range(start, periods=24, freq="h", tz=NONG_FAB_TZ)
        frames.append(idx)
        weights.extend([calendar.monthrange(year, month)[1]] * 24)
    return pd.DatetimeIndex(np.concatenate([f.values for f in frames]), tz=NONG_FAB_TZ), np.asarray(
        weights, dtype=float
    )


def _sky(year: int) -> tuple[pd.DatetimeIndex, pd.DataFrame, np.ndarray, pd.Series]:
    """Clear-sky irradiance, solar position and extraterrestrial radiation for
    the representative year. Computed once and reused for every candidate
    orientation - the sky does not depend on where the panels point, and
    recomputing it per candidate is what would make a sweep slow."""
    index, day_weights = _representative_index(year)
    lat, lon = nong_fab_site_location()
    sky = compute_clearsky_and_position(index, lat, lon, tz=NONG_FAB_TZ)
    dni_extra = pvlib.irradiance.get_extra_radiation(index)
    return index, sky, day_weights, dni_extra


def _poa_kwh_per_m2(sky: pd.DataFrame, dni_extra: pd.Series, weights: np.ndarray, tilt: float, azimuth: float) -> float:
    """Annual plane-of-array irradiance for one orientation, in kWh/m2.

    Hay-Davies rather than isotropic: it splits the diffuse into circumsolar and
    horizon terms, which is the part that distinguishes orientations near the
    optimum. An isotropic sky would flatten exactly the differences being
    measured here.
    """
    total = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        solar_zenith=sky["zenith_deg"],
        solar_azimuth=sky["azimuth_deg"],
        dni=sky["dni_clearsky"],
        ghi=sky["ghi_clearsky"],
        dhi=sky["dhi_clearsky"],
        dni_extra=dni_extra,
        albedo=DEFAULT_ALBEDO,
        model="haydavies",
    )
    poa = total["poa_global"].to_numpy()
    poa = np.nan_to_num(poa, nan=0.0, posinf=0.0, neginf=0.0)
    # Each sample is one hour of a mid-month day standing in for that whole
    # month, hence x days-in-month; /1000 converts W/m2-hours to kWh/m2.
    return float(np.sum(poa * weights) / 1000.0)


def _shading_loss_pct(
    sky: pd.DataFrame, weights: np.ndarray, tilt: float, azimuth: float, row_pitch_m: float, slant_height_m: float
) -> float:
    """Clear-sky-energy-weighted inter-row shading loss at this geometry.

    Weighted by GHI for the same reason `features.shading.annual_shading_loss_pct`
    is: the geometrically dramatic shading just after sunrise happens when there
    is almost no energy to lose, and a time-average would let it dominate.
    """
    elevation = sky["elevation_deg"].to_numpy()
    solar_azimuth = sky["azimuth_deg"].to_numpy()
    ghi = np.nan_to_num(sky["ghi_clearsky"].to_numpy(), nan=0.0)

    shaded = np.array(
        [
            row_shaded_fraction(tilt, azimuth, row_pitch_m, slant_height_m, float(e), float(a))
            if g > 0.0
            else 0.0
            for e, a, g in zip(elevation, solar_azimuth, ghi)
        ]
    )
    weighted_ghi = ghi * weights
    denominator = float(np.sum(weighted_ghi))
    if denominator <= 0.0:
        return 0.0
    return 100.0 * float(np.sum(weighted_ghi * shaded)) / denominator


@dataclass(frozen=True)
class ZoneOrientationReport:
    """Current versus best-available, for one zone.

    `current_is_measured` is the field that decides how much of this can be
    said out loud. config/assets.yaml carries `tilt_deg: null` for every zone
    with the comment "not measured - SLD is electrical-only", so today the
    "current" side is an ASSUMED angle, and the gap below is the gap against an
    assumption. The optimum itself is unaffected by that - it is real either
    way, and it is what the unbuilt expansion phases should be designed to.
    """

    zone_id: str
    current: OrientationYield
    optimum: OrientationYield
    row_pitch_m: float
    slant_height_m: float
    current_is_measured: bool

    @property
    def gain_pct(self) -> float:
        """How much more the array would collect at the optimum, in percent.

        Only a claim about the real array when `current_is_measured` is True.
        Otherwise it is "how far the assumed angle sits from the best one",
        which is worth knowing but is not a finding about the hardware.
        """
        base = self.current.effective_kwh_per_m2
        if base <= 0.0:
            return 0.0
        return (self.optimum.effective_kwh_per_m2 / base - 1.0) * 100.0


def zone_geometry(zone_id: str) -> tuple[float, float, float, float]:
    """(tilt, azimuth, row_pitch_m, slant_height_m) currently modelled, from the
    same layout generator the 3D view and the shading model use - so the
    "current" side of this comparison is the array this system already believes
    in, not a second description of it that could drift."""
    layout = generate_zone_layout(zone_id)
    panel = layout.panels[0]
    return panel.tilt_deg, panel.azimuth_deg, layout.row_pitch_m, panel.slant_height_m


def orientation_is_measured(zone_id: str) -> bool:
    """Whether this zone's tilt AND azimuth came from the project's own records
    rather than from `panel_geometry`'s defaults.

    Both must be present: a measured tilt paired with a guessed azimuth still
    makes "you are losing X kWh" an unsupportable claim.
    """
    zone = load_assets().zone(zone_id)
    return zone.tilt_deg is not None and zone.azimuth_deg is not None


def evaluate(
    tilt: float, azimuth: float, row_pitch_m: float, slant_height_m: float, year: int | None = None
) -> OrientationYield:
    """One orientation, evaluated on its own. Convenience for tests and for
    pricing a specific proposal rather than searching."""
    year = year or datetime.now(dt_timezone.utc).year
    _, sky, weights, dni_extra = _sky(year)
    return OrientationYield(
        tilt_deg=tilt,
        azimuth_deg=azimuth,
        poa_kwh_per_m2=_poa_kwh_per_m2(sky, dni_extra, weights, tilt, azimuth),
        shading_loss_pct=_shading_loss_pct(sky, weights, tilt, azimuth, row_pitch_m, slant_height_m),
    )


@lru_cache(maxsize=16)
def optimise_zone(
    zone_id: str,
    year: int | None = None,
    tilt_range: tuple[float, float] = (0.0, 40.0),
    azimuth_range: tuple[float, float] = (90.0, 270.0),
) -> ZoneOrientationReport:
    """Sweep tilt x azimuth for one zone and report the current angle against
    the best.

    Cached: the sweep evaluates ~1,500 candidates and takes several seconds, and
    the answer depends only on the sun path and the zone's geometry - neither of
    which changes between requests. Without this, three zones would make a
    single page load cost fifteen seconds of arithmetic that never varies.

    Returns a frozen dataclass, so a caller cannot mutate the shared result.

    INVALIDATION: the zone geometry it reads (tilt, azimuth, row pitch) is
    user-editable through the settings registry, so
    `settings_service.apply_effective_settings` clears this alongside
    `annual_shading_loss_pct`. Skipping that would leave a tilt edit answering
    with the pre-edit sweep for the life of the process.

    Tilt is capped at 40 degrees: past that, at this latitude, POA falls while
    wind load and self-shading both climb, so the extra range would only add
    candidates that cannot win. Azimuth spans east through west - a
    north-facing array in the northern hemisphere is not a design anyone would
    consider, and including it would only widen the search.
    """
    year = year or datetime.now(dt_timezone.utc).year
    tilt_built, azimuth_built, row_pitch_m, slant_height_m = zone_geometry(zone_id)
    _, sky, weights, dni_extra = _sky(year)

    def yield_at(tilt: float, azimuth: float) -> OrientationYield:
        return OrientationYield(
            tilt_deg=tilt,
            azimuth_deg=azimuth,
            poa_kwh_per_m2=_poa_kwh_per_m2(sky, dni_extra, weights, tilt, azimuth),
            shading_loss_pct=_shading_loss_pct(sky, weights, tilt, azimuth, row_pitch_m, slant_height_m),
        )

    tilts = np.arange(tilt_range[0], tilt_range[1] + TILT_STEP_DEG / 2, TILT_STEP_DEG)
    azimuths = np.arange(azimuth_range[0], azimuth_range[1] + AZIMUTH_STEP_DEG / 2, AZIMUTH_STEP_DEG)

    best: OrientationYield | None = None
    for azimuth in azimuths:
        for tilt in tilts:
            candidate = yield_at(float(tilt), float(azimuth))
            if best is None or candidate.effective_kwh_per_m2 > best.effective_kwh_per_m2:
                best = candidate
    assert best is not None  # the grid is never empty - both ranges are non-degenerate

    return ZoneOrientationReport(
        zone_id=zone_id,
        current=yield_at(tilt_built, azimuth_built),
        optimum=best,
        row_pitch_m=row_pitch_m,
        slant_height_m=slant_height_m,
        current_is_measured=orientation_is_measured(zone_id),
    )
