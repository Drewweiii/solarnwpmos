"""GET /orientation: the sweep reaches the wire, and the caveats reach it too.

The physics is tested in `simulation/tests/test_tilt_optimizer.py`. What matters
here is that the route does not quietly drop the two things that decide how the
numbers may be read - that the array's real angle was never surveyed, and that
the rest of the site still runs on a different irradiance model.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_orientation_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/orientation").status_code == 401


def test_a_viewer_may_read_it(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        assert client.get("/orientation", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_every_zone_gets_a_current_and_an_optimum(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/orientation", headers={"Authorization": f"Bearer {token}"}).json()

    assert {z["zone_id"] for z in body["zones"]} == {"GIS", "ISB", "Jetty"}
    for zone in body["zones"]:
        assert 0.0 <= zone["optimum"]["tilt_deg"] <= 40.0
        assert zone["optimum"]["effective_kwh_per_m2"] > 0
        # The optimum is the best of the sweep, so it can never lose to the
        # current angle - a negative gain would mean the search missed it.
        assert zone["gain_pct"] >= -1e-9


def test_the_response_says_the_orientation_was_never_surveyed(app, token_factory):
    """The single most important field on this route. Without it a reader sees
    "you could gain 3.7%" and reasonably concludes somebody measured the array,
    when assets.yaml says `tilt_deg: null` for every zone."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/orientation", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["any_unmeasured"] is True
    assert all(z["current_is_measured"] is False for z in body["zones"])
    assert "ยังไม่เคยวัด" in body["unmeasured_note"]


def test_it_says_the_rest_of_the_site_still_uses_a_different_model(app, token_factory):
    """This route adds plane-of-array irradiance; /financial and the Energy
    Report still run on GHI. Two pages quoting different physics without saying
    so is how a reader ends up trusting a comparison that was never made."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/orientation", headers={"Authorization": f"Bearer {token}"}).json()

    assert "GHI" in body["pipeline_note"]


def test_jetty_carries_the_structural_caveat_and_the_others_do_not(app, token_factory):
    """Jetty's azimuth follows the trestle, so its gap describes a constraint
    rather than an action. GIS and ISB have no such excuse and get no note."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/orientation", headers={"Authorization": f"Bearer {token}"}).json()

    by_zone = {z["zone_id"]: z for z in body["zones"]}
    assert by_zone["Jetty"]["note"] is not None
    assert "สะพาน" in by_zone["Jetty"]["note"]
    assert by_zone["GIS"]["note"] is None
