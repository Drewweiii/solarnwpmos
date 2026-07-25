"""Rear-side gain for the bifacial modules actually installed (project H).

The assertions worth having are the ones about DIRECTION and SENSITIVITY, not
the exact percentages: the numbers rest on assumed albedo and mounting height,
so pinning them to two decimals would be pinning a guess. What must hold is that
the model responds to its inputs the way physics says it should.
"""

from __future__ import annotations

import pytest

from nongfab_features.bifacial import (
    ALBEDO_BY_GROUND,
    DATASHEET_BIFACIALITY,
    annual_rear_gain,
    ground_kind_for_zone,
)

YEAR = 2026
PITCH = 3.0
SLANT = 1.3


def gain(ground_kind: str, tilt: float = 10.0):
    return annual_rear_gain(tilt, 180.0, PITCH, SLANT, ground_kind, YEAR)


def test_a_darker_ground_reflects_less_onto_the_rear():
    """Albedo is the dominant term, so this ordering is the model's backbone.
    Water reflects a fraction of what a pale roof does; if these ever came out
    equal, albedo would not be reaching the calculation at all."""
    assert gain("water").gain_pct < gain("ground").gain_pct < gain("rooftop").gain_pct


def test_the_jetty_over_water_gains_far_less_than_the_land_zones():
    """The site-specific finding. Jetty's panels sit above open sea, and a
    single site-wide bifacial uplift - the tempting shortcut - would overstate
    that zone by several times."""
    assert gain("water").gain_pct < 0.5 * gain("ground").gain_pct


def test_the_reported_band_carries_the_datasheets_own_tolerance():
    """Trina rates bifaciality at 80 +/- 5%, so the answer cannot be more
    precise than that. The band exists to stop a single number being read as
    exact."""
    result = gain("ground")
    assert result.gain_pct_low < result.gain_pct < result.gain_pct_high
    # The band is the +/-5% on 80%, i.e. +/-6.25% relative.
    assert result.gain_pct_high / result.gain_pct == pytest.approx(0.85 / 0.80, rel=1e-6)


def test_gain_scales_with_the_bifaciality_factor():
    a = annual_rear_gain(10.0, 180.0, PITCH, SLANT, "ground", YEAR, bifaciality=DATASHEET_BIFACIALITY)
    b = annual_rear_gain(10.0, 180.0, PITCH, SLANT, "ground", YEAR, bifaciality=DATASHEET_BIFACIALITY / 2)
    assert b.gain_pct == pytest.approx(a.gain_pct / 2, rel=1e-6)


def test_the_gain_is_a_plausible_size_not_a_runaway():
    """A view-factor model with a bad geometry term can produce absurd rear
    irradiance. Real bifacial installations report roughly 3-20% depending on
    albedo; anything outside that is a bug, not a discovery."""
    for kind in ALBEDO_BY_GROUND:
        assert 0.0 < gain(kind).gain_pct < 25.0


def test_each_zone_is_matched_to_what_is_actually_under_it():
    assert ground_kind_for_zone("Jetty") == "water"
    assert ground_kind_for_zone("ISB") == "rooftop"
    assert ground_kind_for_zone("GIS") == "ground"
