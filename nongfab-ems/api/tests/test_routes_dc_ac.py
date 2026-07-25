"""GET /dc-ac: the clipping measurement and the headroom finding reach the wire.

The physics lives in `simulation/tests/test_dc_ac_ratio.py`. What matters here is
that the route keeps the two things that stop the numbers being misread - that
this site barely clips despite ratios that look aggressive, and that no
"optimal ratio" is claimed while CAPEX is still an estimate.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_dc_ac_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/dc-ac").status_code == 401


def test_every_zone_reports_its_built_ratio_and_a_curve(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/dc-ac", headers={"Authorization": f"Bearer {token}"}).json()

    assert {z["zone_id"] for z in body["zones"]} == {"GIS", "ISB", "Jetty"}
    for zone in body["zones"]:
        assert zone["built"]["dc_ac_ratio"] > 0
        assert len(zone["curve"]) > 5
        assert zone["built"]["delivered_kwh"] > 0


def test_isb_is_flagged_as_having_free_inverter_capacity(app, token_factory):
    """The one actionable item on the page: modules can be added at ISB with no
    inverter spend. If this silently flipped to false the page would still look
    fine and would have lost its only recommendation."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/dc-ac", headers={"Authorization": f"Bearer {token}"}).json()

    isb = next(z for z in body["zones"] if z["zone_id"] == "ISB")
    assert isb["has_headroom"] is True
    assert isb["headroom_kwp"] > 5.0
    assert body["total_headroom_kwp"] >= isb["headroom_kwp"]


def test_the_site_wide_clipping_total_is_small(app, token_factory):
    """Reported so a reader can see for themselves that clipping is not the
    problem here, rather than being told to assume it from the ratios."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/dc-ac", headers={"Authorization": f"Bearer {token}"}).json()

    assert 0.0 <= body["total_clipped_kwh"] < 5_000.0


def test_it_refuses_to_name_an_optimal_ratio_while_capex_is_an_estimate(app, token_factory):
    """More DC always yields more energy, so an "optimum" would be an artefact
    of a placeholder cost. The marginal figure is given instead, which is what a
    real quote can actually be divided by."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/dc-ac", headers={"Authorization": f"Bearer {token}"}).json()

    assert "30,000" in body["no_optimum_note"]
    assert all(z["marginal_kwh_per_added_kwp"] is not None for z in body["zones"])
