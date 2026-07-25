"""Orientation optimiser (project D): does it find the angle physics says it
should, and does it refuse to overclaim about an array nobody measured?

The valuable assertions here are the ones that would still be true if the
implementation were rewritten - the optimum lands near the latitude, facing the
equator, and the module never calls an assumed angle a measured one.
"""

from __future__ import annotations

import pytest
from nongfab_features.clearsky import nong_fab_site_location

from nongfab_simulation.tilt_optimizer import (
    evaluate,
    optimise_zone,
    orientation_is_measured,
    zone_geometry,
)

YEAR = 2026


class TestPhysics:
    def test_the_optimum_tilt_lands_near_the_site_latitude(self):
        """The textbook result for a fixed array: optimal tilt is roughly the
        latitude. Nong Fab sits at 12.7 N, so an optimiser that returns 3 or 30
        degrees has a bug in the transposition, not an interesting finding.

        Deliberately a band rather than an exact number - self-shading and the
        diffuse fraction both pull the true optimum a little off latitude, and
        pinning the exact degree would make this a change-detector."""
        latitude, _ = nong_fab_site_location()
        report = optimise_zone("GIS", year=YEAR)

        assert latitude - 6 <= report.optimum.tilt_deg <= latitude + 8

    def test_the_optimum_faces_the_equator(self):
        """Northern hemisphere: due south, 180 degrees. Any other answer means
        the azimuth convention got flipped somewhere, which is the classic
        transposition bug and is invisible in the total."""
        report = optimise_zone("GIS", year=YEAR)
        assert report.optimum.azimuth_deg == pytest.approx(180.0, abs=5.0)

    def test_tilting_away_from_the_sun_collects_less(self):
        """A sanity check on the direction of the whole model: north-facing at
        this latitude must lose to south-facing. If this ever passes by
        accident, nothing else here means anything."""
        tilt, _, pitch, slant = zone_geometry("GIS")
        south = evaluate(20.0, 180.0, pitch, slant, year=YEAR)
        north = evaluate(20.0, 0.0, pitch, slant, year=YEAR)

        assert north.effective_kwh_per_m2 < south.effective_kwh_per_m2

    def test_steeper_tilt_costs_more_to_self_shading(self):
        """The trade-off the optimum balances: raising tilt gains plane-of-array
        irradiance and gives some of it back to the row in front. If shading
        were flat in tilt, the optimum would just run to the top of the range."""
        _, _, pitch, slant = zone_geometry("GIS")
        shallow = evaluate(5.0, 180.0, pitch, slant, year=YEAR)
        steep = evaluate(35.0, 180.0, pitch, slant, year=YEAR)

        assert steep.shading_loss_pct > shallow.shading_loss_pct

    def test_a_tilted_plane_beats_a_flat_one_at_this_latitude(self):
        _, _, pitch, slant = zone_geometry("GIS")
        flat = evaluate(0.0, 180.0, pitch, slant, year=YEAR)
        tilted = evaluate(13.0, 180.0, pitch, slant, year=YEAR)

        assert tilted.poa_kwh_per_m2 > flat.poa_kwh_per_m2


class TestHonesty:
    def test_no_zone_claims_a_measured_orientation_today(self):
        """config/assets.yaml carries `tilt_deg: null` for every zone with the
        comment "not measured - SLD is electrical-only". Until somebody surveys
        the array, every "you could gain X%" is a statement about an ASSUMED
        angle, and this flag is what stops the UI from saying otherwise.

        This test is expected to change the day a real survey lands - and that
        is the point: it will fail loudly and force the caveat to be revisited
        rather than left stale."""
        for zone_id in ("GIS", "ISB", "Jetty"):
            assert orientation_is_measured(zone_id) is False
            assert optimise_zone(zone_id, year=YEAR).current_is_measured is False

    def test_the_optimum_does_not_depend_on_what_was_built(self):
        """The claim that survives the missing survey. Two zones with identical
        geometry must get the same optimum regardless of their current angles,
        because the optimum comes from the sun path - which is why it is still
        publishable while the gap figure is not."""
        gis = optimise_zone("GIS", year=YEAR)
        jetty = optimise_zone("Jetty", year=YEAR)

        assert gis.optimum.tilt_deg == jetty.optimum.tilt_deg
        assert gis.optimum.azimuth_deg == jetty.optimum.azimuth_deg

    def test_the_gain_is_never_negative_for_a_true_optimum(self):
        """A sweep that returned something worse than the current angle would
        mean the current angle was not in the search space - a silent bug that
        would understate every recommendation."""
        for zone_id in ("GIS", "ISB", "Jetty"):
            assert optimise_zone(zone_id, year=YEAR).gain_pct >= -1e-9


class TestJetty:
    def test_a_west_facing_array_shows_a_real_penalty(self):
        """Jetty's panels follow the trestle and face west, so this is the one
        zone where the modelled gap is large. It is reported as the cost of a
        structural constraint, not as advice to rotate a pier."""
        report = optimise_zone("Jetty", year=YEAR)

        assert report.current.azimuth_deg == pytest.approx(270.0)
        assert report.gain_pct > 1.0
