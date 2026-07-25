"""DC:AC ratio and inverter clipping (project F).

The finding these pin: this site barely clips at all. The ratios look aggressive
on paper (GIS 1.20) but after a ~20% loss stack the AC output rarely reaches the
inverter's rating, so clipping is a rounding error - and the real opportunity is
ISB, whose inverter is LARGER than its array.
"""

from __future__ import annotations

import pytest

from nongfab_simulation.dc_ac_ratio import analyse_zone, headroom_kwp

YEAR = 2026


class TestClipping:
    def test_clipping_rises_with_the_ratio_and_starts_at_zero_below_one(self):
        """The shape the whole analysis depends on. Below 1.0 the array cannot
        reach the inverter's rating at all, so there is nothing to clip; above
        it, clipping grows. A curve that clipped at 0.8 would mean the loss
        stack was being applied in the wrong order."""
        curve = sorted(analyse_zone("GIS", YEAR).curve, key=lambda p: p.dc_ac_ratio)

        below_one = [p for p in curve if p.dc_ac_ratio <= 0.95]
        assert all(p.clipping_loss_pct == pytest.approx(0.0, abs=1e-9) for p in below_one)

        losses = [p.clipping_loss_pct for p in curve]
        assert losses == sorted(losses)
        assert curve[-1].clipping_loss_pct > 0.0

    def test_the_site_barely_clips_as_built(self):
        """The headline, and not what the DC:AC numbers suggest at a glance.
        GIS is at 1.20, which reads as "expect midday clipping" - but the
        ~20% loss stack means the AC side almost never reaches 50 kW, so the
        real loss is a fraction of a percent. Worth pinning: if a future loss
        change made this jump, the array's economics would have changed with
        it."""
        built = analyse_zone("GIS", YEAR).built
        assert built.dc_ac_ratio > 1.1
        assert built.clipping_loss_pct < 1.0

    def test_specific_yield_falls_as_the_array_outgrows_its_inverter(self):
        """Energy per kWp is what makes different-sized arrays comparable, and
        it must decline with the ratio - that decline IS the cost of
        over-sizing."""
        curve = sorted(analyse_zone("GIS", YEAR).curve, key=lambda p: p.dc_ac_ratio)
        assert curve[-1].specific_yield_kwh_per_kwp < curve[0].specific_yield_kwh_per_kwp


class TestHeadroom:
    def test_isb_has_free_inverter_capacity_and_the_others_do_not(self):
        """The actionable finding: ISB's inverter is bigger than its array, so
        modules can be added there without buying an inverter. GIS and Jetty are
        already past 1.0 and get zero rather than a negative number, which would
        read as a deficit to make up."""
        assert analyse_zone("ISB", YEAR).has_headroom is True
        assert headroom_kwp("ISB", YEAR) > 5.0

        for zone_id in ("GIS", "Jetty"):
            assert analyse_zone(zone_id, YEAR).has_headroom is False
            assert headroom_kwp(zone_id, YEAR) == 0.0

    def test_the_next_kwp_is_worth_less_on_an_oversized_array(self):
        """Why the marginal figure is reported rather than an optimum: the same
        module earns less once the inverter is already saturated, and that is
        the number a real CAPEX quote has to be divided by."""
        report = analyse_zone("GIS", YEAR)
        low = report.marginal_kwh_per_added_kwp(0.8)
        high = report.marginal_kwh_per_added_kwp(1.55)

        assert low is not None and high is not None
        assert high < low

    def test_a_ratio_outside_the_swept_range_returns_none_not_a_guess(self):
        assert analyse_zone("GIS", YEAR).marginal_kwh_per_added_kwp(5.0) is None


def test_scaling_from_one_reference_run_matches_the_built_case_exactly():
    """The optimisation that made this usable: the curve is scaled from a single
    pipeline run because power is strictly linear in capacity. The built point
    is computed the same way, so it must land on the array's real capacity -
    if scaling were wrong, every number here would be wrong together and
    silently."""
    from nongfab_common.assets import load_assets

    report = analyse_zone("ISB", YEAR)
    assert report.built.dc_capacity_kwp == pytest.approx(load_assets().zone("ISB").dc_capacity_kwp)
    assert report.built.delivered_kwh > 0
