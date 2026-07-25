"""GET /bifacial: the rear-side estimate, and the label that keeps it honest."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_bifacial_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/bifacial").status_code == 401


def test_every_zone_reports_a_gain_and_what_it_assumed(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/bifacial", headers={"Authorization": f"Bearer {token}"}).json()

    assert body["bifaciality"] == 0.80
    assert {z["zone_id"] for z in body["zones"]} == {"GIS", "ISB", "Jetty"}
    for zone in body["zones"]:
        assert 0.0 < zone["gain_pct"] < 25.0
        # The two assumed inputs travel with the number they produced, so a
        # reader can see what the estimate rests on without leaving the row.
        assert zone["albedo_assumed"] > 0
        assert zone["height_m_assumed"] > 0


def test_the_jetty_is_recognised_as_sitting_over_water(app, token_factory):
    """The zone where a single site-wide uplift would be most wrong."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/bifacial", headers={"Authorization": f"Bearer {token}"}).json()

    by_zone = {z["zone_id"]: z for z in body["zones"]}
    assert by_zone["Jetty"]["ground_kind"] == "water"
    assert by_zone["Jetty"]["gain_pct"] < by_zone["GIS"]["gain_pct"]


def test_it_says_plainly_that_the_gain_is_not_in_the_published_figures(app, token_factory):
    """The whole reason this is a separate route rather than an uplift applied
    to the yield: the published energy stays monofacial and conservative until
    somebody measures albedo and mounting height."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        body = client.get("/bifacial", headers={"Authorization": f"Bearer {token}"}).json()

    assert "ไม่ได้" in body["not_applied_note"]
    assert "albedo" in body["not_applied_note"]
    assert body["unlock_note"]
