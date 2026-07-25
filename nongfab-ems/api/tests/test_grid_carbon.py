"""Hour-of-day grid carbon intensity: the merit-order model and its guardrails.

The thing worth testing here is not "does it return numbers" but the two claims
the panel makes: that the modelled curve REDISTRIBUTES the published emission
factor rather than replacing it, and that the marginal fuel gets dirtier as the
system load climbs. Both are asserted directly below, because both are what
would make the published carbon figures wrong if they broke.

The load curve used throughout is a synthetic day with a real Thai shape - a
low overnight trough and an evening peak - not captured EGAT data, since what
is under test is the arithmetic on top of any load curve.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from nongfab_api import grid_carbon
from nongfab_api.egat_grid import ICT, GridPoint, GridSnapshot

DAY = datetime(2026, 7, 25, tzinfo=ICT)


def _load_at(hour: float) -> float:
    """A plausible Thai daily load curve: ~22 GW overnight, ~34 GW at 20:00."""
    return 28_000.0 + 6_000.0 * math.sin(math.pi * (hour - 4.0) / 16.0) - 2_000.0 * math.cos(math.pi * hour / 12.0)


def _day_points(step_minutes: int = 15) -> list[GridPoint]:
    points = []
    for minute in range(0, 24 * 60, step_minutes):
        points.append(GridPoint(at=DAY + timedelta(minutes=minute), mw=_load_at(minute / 60.0)))
    return points


EVEN_MIX = {"natural_gas": 0.5, "coal_lignite": 0.25, "imported": 0.25}

# Same stack with a sliver of peaking oil on top. Thailand's real mix has
# essentially none, which is exactly why gas ends up marginal around the clock
# there - this variant exists to prove the mechanism still switches fuels when
# a mix actually puts a different unit at the top.
MIX_WITH_PEAKER = {"natural_gas": 0.45, "coal_lignite": 0.25, "imported": 0.25, "oil": 0.05}


class TestBands:
    def test_each_band_holds_its_share_of_the_days_energy(self):
        """The whole model rests on this: a fuel with 25% of generation must
        occupy a slab of the load-duration curve whose AREA is 25%, not whose
        height is 25%. Getting that wrong would put the wrong fuel on the
        margin at every hour."""
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, EVEN_MIX)
        total = sum(loads)

        by_key = {b.fuel.key: b for b in bands}
        for key, share in EVEN_MIX.items():
            band = by_key[key]
            area = grid_carbon._energy_between(loads, band.bottom_mw, band.top_mw)
            assert area / total == pytest.approx(share, abs=0.005)

    def test_bands_stack_in_merit_order_with_no_gaps(self):
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, EVEN_MIX)

        assert [b.fuel.key for b in bands] == ["imported", "coal_lignite", "natural_gas"]
        assert bands[0].bottom_mw == 0.0
        for lower, upper in zip(bands, bands[1:]):
            assert lower.top_mw == upper.bottom_mw
        assert bands[-1].top_mw == pytest.approx(max(loads))

    def test_an_empty_or_unusable_mix_yields_no_bands_rather_than_a_crash(self):
        loads = [p.mw for p in _day_points()]
        assert grid_carbon.build_bands(loads, {}) == []
        assert grid_carbon.build_bands(loads, {"nonsense": 1.0}) == []
        assert grid_carbon.build_bands(loads, {"natural_gas": 0.0}) == []
        assert grid_carbon.build_bands([], EVEN_MIX) == []

    def test_the_shipped_shares_are_eppos_published_2566_figures(self):
        """Pins the defaults to the published table rather than to whatever
        looked plausible. EPPO's 2566 national generation was 219,540.04 GWh and
        the per-fuel GWh column reconciles to it exactly, which is what makes
        these usable as defaults at all - so the shares must sum to 100 and
        match that source."""
        assert grid_carbon.DEFAULT_MIX == {
            "natural_gas": 0.5861,
            "coal_lignite": 0.1310,
            "imported": 0.1494,
            "renewables": 0.1042,
            "hydro": 0.0292,
            "oil": 0.0001,
        }
        assert sum(grid_carbon.DEFAULT_MIX.values()) == pytest.approx(1.0)

    def test_imports_are_the_national_share_not_egats_own_system_share(self):
        """The trap this avoids: EGAT publishes a second fuel table covering
        only plant EGAT itself runs, where imports are ~1%. Stacking that
        against a NATIONAL load curve would push ~14% of clean imported hydro
        out of the stack and misstate the whole merit order."""
        assert grid_carbon.DEFAULT_MIX["imported"] > 0.10


class TestMargin:
    def test_the_marginal_fuel_never_gets_cleaner_as_the_system_climbs(self):
        """The invariant that must always hold: adding load can only reach UP
        the merit order. It is deliberately weaker than "the peak is dirtier
        than the trough" because with Thailand's actual mix it is not - see the
        next test."""
        loads = sorted(p.mw for p in _day_points())
        bands = grid_carbon.build_bands(loads, EVEN_MIX)

        ranks = [grid_carbon.marginal_fuel(bands, load).merit_rank for load in loads]  # type: ignore[union-attr]
        assert ranks == sorted(ranks)

    def test_with_thailands_mix_gas_is_marginal_for_essentially_the_whole_day(self):
        """Not a defect - a finding, and the one that makes this panel worth
        having. Thai demand never falls far enough for the gas fleet to come off
        the margin, so solar here displaces GAS whenever it produces, not the
        grid average. That is precisely what the flat annual factor hides.

        The only exception is the topmost sliver of the daily peak, where EPPO's
        0.01% oil share forms a hair-thin band - see the next test for why that
        sliver is left in rather than rounded away."""
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, grid_carbon.DEFAULT_MIX)

        fuels = [grid_carbon.marginal_fuel(bands, load).key for load in loads]  # type: ignore[union-attr]
        assert set(fuels) <= {"natural_gas", "oil"}
        assert fuels.count("natural_gas") / len(fuels) > 0.9

    def test_oils_hair_thin_band_sits_at_the_very_top_of_the_peak(self):
        """EPPO puts oil at 0.01% of annual generation, so its band is ~80 MW
        wide at the top of a 36 GW curve and only the daily peak reaches it.

        Left in deliberately, with the caveat stated: applying an ANNUAL share
        to a SINGLE day implies oil runs a sliver every day, when in reality it
        runs on a handful of peak days a year. So the peak hour's 'oil' label
        over-attributes on a typical day. It is kept because dropping the
        cheapest-to-drop peaker would also drop the model's only ability to show
        a peaking unit at all, and because it moves the intensity by a hair -
        not because it is exactly right."""
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, grid_carbon.DEFAULT_MIX)
        oil = next(b for b in bands if b.fuel.key == "oil")

        assert oil.top_mw == pytest.approx(max(loads))
        assert (oil.top_mw - oil.bottom_mw) / max(loads) < 0.01
        assert grid_carbon.marginal_fuel(bands, min(loads)).key == "natural_gas"  # type: ignore[union-attr]

    def test_a_mix_with_peaking_oil_does_switch_fuels_across_the_day(self):
        """The mechanism itself works; it simply has nothing to switch to under
        the Thai mix. Give the stack a peaker and the evening peak lands on it."""
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, MIX_WITH_PEAKER)

        trough = grid_carbon.marginal_fuel(bands, min(loads))
        peak = grid_carbon.marginal_fuel(bands, max(loads))

        assert trough is not None and peak is not None
        assert trough.merit_rank < peak.merit_rank
        assert peak.key == "oil"
        assert peak.ef_kg_per_kwh > trough.ef_kg_per_kwh

    def test_average_intensity_rises_with_load_and_stays_between_the_fuels(self):
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, EVEN_MIX)
        cleanest = min(b.fuel.ef_kg_per_kwh for b in bands)
        dirtiest = max(b.fuel.ef_kg_per_kwh for b in bands)

        low = grid_carbon.average_ef_kg_per_kwh(bands, min(loads))
        high = grid_carbon.average_ef_kg_per_kwh(bands, max(loads))

        assert low is not None and high is not None
        assert low < high
        assert cleanest <= low <= dirtiest
        assert cleanest <= high <= dirtiest

    def test_marginal_is_at_least_the_average_at_the_same_instant(self):
        """A dispatch stack cannot have its marginal unit be cleaner than the
        mix beneath it - if this ever inverts, the merit ordering is broken."""
        loads = [p.mw for p in _day_points()]
        bands = grid_carbon.build_bands(loads, EVEN_MIX)
        for load in loads:
            average = grid_carbon.average_ef_kg_per_kwh(bands, load)
            fuel = grid_carbon.marginal_fuel(bands, load)
            assert average is not None and fuel is not None
            assert fuel.ef_kg_per_kwh >= average - 1e-9


class TestCalibration:
    def test_the_curves_load_weighted_mean_equals_the_published_factor(self):
        """The guardrail. Whatever the mix and whatever the IPCC table say, the
        day's load-weighted average intensity must come out at the published
        GEF - otherwise this page and the Energy Report would be quoting two
        different national carbon figures."""
        points = _day_points()
        published = 0.4758
        curve = grid_carbon.carbon_curve(points, EVEN_MIX, published)

        weighted = sum(p.average_kg_per_kwh * p.load_mw for p in curve)
        total = sum(p.load_mw for p in curve)
        assert weighted / total == pytest.approx(published, rel=1e-6)

    def test_changing_the_published_factor_rescales_the_whole_curve(self):
        points = _day_points()
        low = grid_carbon.carbon_curve(points, EVEN_MIX, 0.4)
        high = grid_carbon.carbon_curve(points, EVEN_MIX, 0.8)

        assert len(low) == len(high)
        for a, b in zip(low, high):
            assert b.average_kg_per_kwh == pytest.approx(a.average_kg_per_kwh * 2.0, rel=1e-6)

    def test_the_shipped_eppo_mix_still_produces_a_calibrated_curve(self):
        """The invariant must hold for the mix that actually ships, not just for
        the tidy test one - an unconfigured deployment still shows a curve whose
        average is the official number."""
        points = _day_points()
        curve = grid_carbon.carbon_curve(points, grid_carbon.DEFAULT_MIX, 0.4758)
        weighted = sum(p.average_kg_per_kwh * p.load_mw for p in curve)
        total = sum(p.load_mw for p in curve)
        assert weighted / total == pytest.approx(0.4758, rel=1e-6)


class TestHourlyAndWeighting:
    def test_hours_collapse_to_at_most_24_rows_carrying_their_sample_count(self):
        curve = grid_carbon.carbon_curve(_day_points(), EVEN_MIX, 0.4758)
        hours = grid_carbon.hourly_means(curve)

        assert len(hours) == 24
        assert [row["hour"] for row in hours] == list(range(24))
        assert sum(int(row["samples"]) for row in hours) == len(curve)

    def test_solar_weighting_only_counts_hours_the_array_produces_in(self):
        """The payoff calculation. Weighting by a daytime-only profile must land
        on the daytime intensity, not the all-day mean - if it matched the flat
        average, the panel would have nothing to say."""
        curve = grid_carbon.carbon_curve(_day_points(), EVEN_MIX, 0.4758)
        hours = grid_carbon.hourly_means(curve)
        daytime = {hour: 100.0 for hour in range(9, 16)}

        weighted = grid_carbon.solar_weighted_ef(hours, daytime, "average_kg_per_kwh")
        flat_mean = sum(float(r["average_kg_per_kwh"]) for r in hours) / len(hours)

        assert weighted is not None
        assert weighted != pytest.approx(flat_mean, rel=1e-6)
        # Daytime load is above the daily mean here, so the daytime grid is
        # dirtier - the direction matters, not just that the numbers differ.
        assert weighted > flat_mean

    def test_the_marginal_factor_solar_earns_exceeds_the_published_average(self):
        """The headline the panel reports. Under Thailand's mix every solar kWh
        displaces gas, whose factor sits well above the annual average the
        Energy Report uses - so the flat factor UNDERSTATES this array."""
        published = 0.4758
        curve = grid_carbon.carbon_curve(_day_points(), grid_carbon.DEFAULT_MIX, published)
        hours = grid_carbon.hourly_means(curve)
        daytime = {hour: 100.0 for hour in range(7, 18)}

        marginal = grid_carbon.solar_weighted_ef(hours, daytime, "marginal_kg_per_kwh")
        assert marginal is not None
        assert marginal > published

    def test_no_overlap_returns_none_rather_than_a_number_from_one_hour(self):
        curve = grid_carbon.carbon_curve(_day_points(), EVEN_MIX, 0.4758)
        hours = grid_carbon.hourly_means(curve)
        assert grid_carbon.solar_weighted_ef(hours, {}) is None
        assert grid_carbon.solar_weighted_ef([], {12: 100.0}) is None


class TestRoute:
    def test_unreachable_upstream_is_honest_empty_not_a_fabricated_curve(self, app, token_factory, monkeypatch):
        monkeypatch.setattr("nongfab_api.routes_grid_carbon._cached_snapshot", _none_snapshot)
        with TestClient(app) as client:
            body = client.get("/grid/carbon", headers=_auth(token_factory)).json()

        assert body["available"] is False
        assert body["hours"] == []
        assert body["reason"]

    def test_a_live_day_returns_hours_calibrated_to_the_published_factor(self, app, token_factory, monkeypatch):
        monkeypatch.setattr("nongfab_api.routes_grid_carbon._cached_snapshot", _fake_snapshot)
        with TestClient(app) as client:
            body = client.get("/grid/carbon", headers=_auth(token_factory)).json()

        assert body["available"] is True
        assert body["day"] == "2026-07-25"
        assert len(body["hours"]) == 24
        assert body["published_ef_kg_per_kwh"] == pytest.approx(0.4758)

        weighted = sum(h["average_kg_per_kwh"] * h["load_mw"] for h in body["hours"])
        total = sum(h["load_mw"] for h in body["hours"])
        assert weighted / total == pytest.approx(0.4758, rel=1e-3)

    def test_an_unconfigured_mix_is_labelled_annual_on_the_wire(self, app, token_factory, monkeypatch):
        """A viewer must be able to tell the split is EPPO's YEARLY average
        rather than the month actually being shown - the shape depends on it,
        and Thai hydrology and gas availability both move seasonally."""
        monkeypatch.setattr("nongfab_api.routes_grid_carbon._cached_snapshot", _fake_snapshot)
        with TestClient(app) as client:
            body = client.get("/grid/carbon", headers=_auth(token_factory)).json()

        assert body["mix_origin"] == "annual"
        assert "2566" in body["mix_note"]
        assert sum(row["share_pct"] for row in body["mix"]) == pytest.approx(100.0)

    def test_solar_only_produces_by_day_so_its_factor_is_the_daytime_one(self, app, token_factory, monkeypatch):
        monkeypatch.setattr("nongfab_api.routes_grid_carbon._cached_snapshot", _fake_snapshot)
        with TestClient(app) as client:
            body = client.get("/grid/carbon", headers=_auth(token_factory)).json()

        produced = [h for h in body["hours"] if h["site_generation_kwh"] > 0.0]
        assert produced, "the clear-sky profile must produce something during the day"
        assert all(6 <= h["hour"] <= 19 for h in produced)
        assert body["solar_weighted_marginal_kg_per_kwh"] is not None
        assert body["marginal_uplift_pct"] is not None

    def test_publishing_a_fuel_share_changes_the_curve_and_the_label(self, app, token_factory, monkeypatch):
        """The mix has to be genuinely wired, not merely stored: pushing the
        grid to mostly-coal must move the intensity somewhere and flip the origin
        label away from the shipped annual figures."""
        monkeypatch.setattr("nongfab_api.routes_grid_carbon._cached_snapshot", _fake_snapshot)
        headers = _auth(token_factory)
        admin = {"Authorization": f"Bearer {token_factory('admin')}"}

        with TestClient(app) as client:
            before = client.get("/grid/carbon", headers=headers).json()
            response = client.put(
                "/settings",
                json={
                    "values": {
                        "gridmix.natural_gas_pct": 10.0,
                        "gridmix.coal_lignite_pct": 80.0,
                        "gridmix.imported_pct": 10.0,
                        "gridmix.renewables_pct": 0.0,
                        "gridmix.hydro_pct": 0.0,
                        "gridmix.oil_pct": 0.0,
                    }
                },
                headers=admin,
            )
            assert response.status_code == 200
            after = client.get("/grid/carbon", headers=headers).json()

        assert after["mix_origin"] == "published"
        assert before["hours"][12]["marginal_kg_per_kwh"] != pytest.approx(after["hours"][12]["marginal_kg_per_kwh"])
        # Calibration must survive the change: the average is still the official
        # figure, only its distribution across the day moved.
        weighted = sum(h["average_kg_per_kwh"] * h["load_mw"] for h in after["hours"])
        total = sum(h["load_mw"] for h in after["hours"])
        assert weighted / total == pytest.approx(0.4758, rel=1e-3)


def _auth(token_factory) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_factory('viewer')}"}


async def _none_snapshot() -> None:
    return None


async def _fake_snapshot() -> GridSnapshot:
    return GridSnapshot(day="2026-07-25", actual=_day_points(), plan=[], peaks=[])
