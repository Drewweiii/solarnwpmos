"""GHI -> plane-of-array (2026-07-25): the transposition that made tilt matter.

Before this, the PV model consumed GHI directly, so a tilted array and a flat
one produced identical yield. These tests pin the behaviour that fixed it, and
the edge cases where a transposition model most easily goes wrong - night, flat
surfaces, and the hemisphere convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from nongfab_features.poa import poa_from_ghi

# Mid-December: the sun is well south, so a south-facing tilt gains clearly.
# Chosen over a summer day on purpose - in July the sun passes north of
# overhead here and a south tilt slightly LOSES at noon, which would make a
# "tilting helps" assertion accidentally false.
WINTER_NOON = pd.date_range("2026-12-15 04:00", periods=6, freq="h", tz="UTC")
GHI = np.array([200.0, 500.0, 800.0, 900.0, 700.0, 300.0])


def test_a_flat_surface_returns_its_input_untouched():
    """Tilt 0 has nothing to transpose and the answer is exactly known, so the
    model is skipped rather than allowed to introduce a rounding error into a
    value that was already correct."""
    out = poa_from_ghi(GHI, WINTER_NOON, 0.0, 180.0)
    assert out == pytest.approx(GHI)


def test_tilting_toward_the_winter_sun_collects_more_than_flat():
    flat = poa_from_ghi(GHI, WINTER_NOON, 0.0, 180.0)
    tilted = poa_from_ghi(GHI, WINTER_NOON, 15.0, 180.0)
    assert tilted.sum() > flat.sum()


def test_facing_away_from_the_equator_collects_less():
    """The hemisphere convention. A north-facing array at 12.7 N must lose to a
    south-facing one - if this passes with the sign flipped, every orientation
    conclusion in the system is backwards and nothing else would reveal it."""
    south = poa_from_ghi(GHI, WINTER_NOON, 20.0, 180.0)
    north = poa_from_ghi(GHI, WINTER_NOON, 20.0, 0.0)
    assert north.sum() < south.sum()


def test_night_stays_night():
    """Erbs can emit a small positive diffuse at zenith angles past 90 degrees.
    Letting that through would have the array generating after dark, which is
    the kind of error that looks plausible in a total and absurd in a chart."""
    night = pd.date_range("2026-12-15 16:00", periods=4, freq="h", tz="UTC")
    out = poa_from_ghi(np.zeros(4), night, 15.0, 180.0)
    assert out.tolist() == [0.0, 0.0, 0.0, 0.0]


def test_a_naive_index_is_read_as_utc_rather_than_guessed():
    """Every upstream source here publishes UTC and some hand over a tz-naive
    index. Silently picking a different zone would shift the sun by hours and
    corrupt every value, so the assumption is made once, here."""
    naive = WINTER_NOON.tz_localize(None)
    assert poa_from_ghi(GHI, naive, 15.0, 180.0) == pytest.approx(poa_from_ghi(GHI, WINTER_NOON, 15.0, 180.0))


def test_nans_become_zero_rather_than_poisoning_the_series():
    out = poa_from_ghi(np.array([np.nan, 500.0, np.inf, 700.0, 0.0, 100.0]), WINTER_NOON, 15.0, 180.0)
    assert np.isfinite(out).all()
    assert out[0] == 0.0 and out[2] == 0.0
