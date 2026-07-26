"""GET /provenance (2026-07-26, project O) - the chain behind a published
number, and the guarantee that a setting's origin is read live rather than
restated."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nongfab_api.provenance import BY_VALUE_KEY, validate_registry


def test_provenance_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/provenance/financial.payback_years").status_code == 401


def test_provenance_is_viewer_level(app, token_factory):
    """Seeing that a number rests on a placeholder is exactly what a public
    dashboard should not hide behind a login."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/provenance/financial.payback_years", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_unknown_key_names_the_available_ones(app, token_factory):
    # These keys are written by hand at call sites; a typo is the likeliest way
    # to land here, so the 404 has to be actionable.
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/provenance/nope.not.a.key", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert "financial.payback_years" in resp.json()["detail"]


def test_the_index_lists_every_traceable_number(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/provenance", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert sorted(BY_VALUE_KEY) == body["keys"]
    assert body["intro"]


def test_a_setting_step_reports_the_registry_origin_not_a_stored_copy(app, token_factory):
    """The one rule this feature lives by. CAPEX is a documented placeholder in
    settings_registry, and the chain must say so by READING it - if this ever
    came from hand-written text it would keep saying whatever it said on the day
    it was written."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/provenance/financial.payback_years", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    capex = next(s for s in body["steps"] if s["setting_key"] == "financial.capex_per_kwp_thb")
    assert capex["origin"] == "placeholder"
    assert capex["origin_label"]
    # The registry's own note and current default travel with it, so the popup
    # can show what the value actually is right now.
    assert capex["registry_note"]
    assert capex["default_value"] == 30000.0
    assert capex["unit"]


def test_the_headline_is_the_weakest_link_not_the_best_one(app, token_factory):
    """A number is only as sound as its shakiest input. Payback's chain contains
    an as-built model and a user-confirmed BOI figure, but also a placeholder
    CAPEX - so the headline must be 'placeholder'."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get("/provenance/financial.payback_years", headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    origins = {s["origin"] for s in body["steps"]}
    assert "confirmed" in origins or "as-built" in origins  # the chain does contain stronger links
    assert body["weakest_origin"] == "placeholder"
    assert body["weakest_note"]


def test_every_entry_carries_a_caveat_and_a_resolvable_chain(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        for key in BY_VALUE_KEY:
            body = client.get(f"/provenance/{key}", headers={"Authorization": f"Bearer {token}"}).json()
            assert body["caveat"], f"{key} has no caveat"
            assert body["steps"], f"{key} has no steps"
            # Every step resolves to an origin - a link with none would be a
            # hole in the chain presented as if it were complete.
            assert all(s["origin"] for s in body["steps"]), f"{key} has a step with no origin"


def test_a_renamed_setting_breaks_the_build_rather_than_the_answer(monkeypatch):
    """validate_registry runs at import. Simulate a setting being renamed out
    from under a step and confirm it raises instead of silently serving a chain
    with a hole in it."""
    import nongfab_api.provenance as prov

    monkeypatch.setitem(prov.BY_KEY, "financial.capex_per_kwp_thb", None)
    monkeypatch.delitem(prov.BY_KEY, "financial.capex_per_kwp_thb")
    try:
        prov.validate_registry()
    except ValueError as exc:
        assert "financial.capex_per_kwp_thb" in str(exc)
    else:
        raise AssertionError("validate_registry accepted a missing setting key")


def test_the_shipped_registry_is_valid():
    validate_registry()
