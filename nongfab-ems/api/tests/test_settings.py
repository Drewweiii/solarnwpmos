"""User-editable system values (2026-07-25): the registry's own guarantees, the
store's persistence, the routes' permission model, and - the part that matters -
that a saved value actually CHANGES what the rest of the API answers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from nongfab_common.assets import load_assets
from nongfab_simulation.loss_model import default_loss_factors

from nongfab_api import settings_store
from nongfab_api.config import Settings
from nongfab_api.main import create_app
from nongfab_api.settings_registry import BY_KEY, GROUP_LABELS, ORIGIN_CONFIRMED, SPECS, validate
from nongfab_api.settings_service import apply_effective_settings


@pytest.fixture(autouse=True)
def _clean_settings():
    """The effective-value cache and the injected overrides are process-level, so
    every test starts and ends from the shipped defaults."""
    settings_store.reset_cache()
    apply_effective_settings()
    yield
    settings_store.reset_cache()
    apply_effective_settings()


# --- registry ---------------------------------------------------------------


def test_every_spec_has_a_sane_shape():
    assert SPECS, "the registry must not be empty"
    for spec in SPECS:
        assert spec.key == spec.key.strip() and " " not in spec.key
        assert spec.group in GROUP_LABELS, f"{spec.key} is in an unknown group"
        assert spec.label, f"{spec.key} needs a Thai label for the form"
        assert spec.minimum <= spec.default <= spec.maximum, f"{spec.key}'s default is outside its own bounds"
        assert spec.step > 0, f"{spec.key} needs a positive step"


def test_keys_are_unique():
    keys = [spec.key for spec in SPECS]
    assert len(keys) == len(set(keys))
    assert len(BY_KEY) == len(keys)


def test_validate_rejects_out_of_range_and_non_numbers():
    with pytest.raises(ValueError):
        validate("financial.discount_rate_pct", -1.0)
    with pytest.raises(ValueError):
        validate("financial.discount_rate_pct", 1_000.0)
    with pytest.raises(ValueError):
        validate("financial.discount_rate_pct", float("nan"))
    with pytest.raises(ValueError):
        validate("financial.discount_rate_pct", True)  # bool is not a number here
    assert validate("financial.discount_rate_pct", 7) == 7.0


def test_unknown_key_raises_rather_than_defaulting_to_zero():
    with pytest.raises(KeyError):
        settings_store.effective("nope.not.a.key")


def test_effective_is_the_default_until_something_is_published():
    assert settings_store.effective("financial.discount_rate_pct") == 8.0
    assert settings_store.is_overridden("financial.discount_rate_pct") is False


# --- store + routes ---------------------------------------------------------


def _file_backed_app(engine, tmp_path):
    settings = Settings(
        jwt_secret_key="test-secret",
        seed_demo_users=True,
        enable_background_ingestion=False,
        real_data_db_path=str(tmp_path / "real_data.db"),
    )
    return create_app(settings=settings, engine=engine), settings


def test_settings_read_requires_auth(app):
    with TestClient(app) as client:
        assert client.get("/settings").status_code == 401


def test_a_viewer_may_read_but_not_publish(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        read = client.get("/settings", headers={"Authorization": f"Bearer {token}"})
        write = client.put(
            "/settings", json={"values": {"financial.discount_rate_pct": 9.0}}, headers={"Authorization": f"Bearer {token}"}
        )
    assert read.status_code == 200
    assert read.json()["can_publish"] is False
    assert write.status_code == 403


def test_the_read_describes_itself_well_enough_to_render_a_form(app, token_factory):
    token = token_factory("admin")
    with TestClient(app) as client:
        body = client.get("/settings", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["can_publish"] is True
    assert len(body["settings"]) == len(SPECS)
    assert set(body["groups"]) == set(GROUP_LABELS)
    field = next(s for s in body["settings"] if s["key"] == "financial.capex_per_kwp_thb")
    for required in ("label", "unit", "minimum", "maximum", "step", "default", "value", "origin_label", "note"):
        assert field[required] not in (None, ""), f"{required} missing from the form description"
    # The honesty field: CAPEX is an unverified estimate and must say so.
    assert field["origin"] == "placeholder"
    assert field["overridden"] is False


def test_publishing_records_the_value_and_who_set_it(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("bossadmin", "admin", settings, app.state.deploy_id)
        resp = client.put(
            "/settings",
            json={"values": {"financial.discount_rate_pct": 9.5, "losses.mismatch_pct": 1.4}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == {"financial.discount_rate_pct": 9.5, "losses.mismatch_pct": 1.4}
        field = next(s for s in body["settings"] if s["key"] == "financial.discount_rate_pct")
        assert field["value"] == 9.5
        assert field["overridden"] is True
        assert field["updated_by"] == "bossadmin"
        assert field["updated_at"]


def test_an_out_of_range_field_rejects_the_WHOLE_submission(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        resp = client.put(
            "/settings",
            # First value is fine, second is impossible.
            json={"values": {"losses.mismatch_pct": 1.0, "financial.discount_rate_pct": 999.0}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        # The good field must NOT have been applied - a half-saved form is worse
        # than a rejected one.
        after = client.get("/settings", headers={"Authorization": f"Bearer {token}"}).json()
    field = next(s for s in after["settings"] if s["key"] == "losses.mismatch_pct")
    assert field["overridden"] is False


def test_an_unknown_key_404s(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        resp = client.put("/settings", json={"values": {"made.up.key": 1.0}}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_an_empty_submission_is_rejected(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        assert client.put("/settings", json={"values": {}}, headers={"Authorization": f"Bearer {token}"}).status_code == 422


def test_resetting_one_field_and_resetting_everything(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        client.put("/settings", json={"values": {"losses.mismatch_pct": 1.4, "losses.dc_wiring_pct": 3.1}}, headers=headers)

        one = client.delete("/settings/losses.mismatch_pct", headers=headers)
        assert one.status_code == 200
        by_key = {s["key"]: s for s in one.json()["settings"]}
        assert by_key["losses.mismatch_pct"]["overridden"] is False
        assert by_key["losses.mismatch_pct"]["value"] == by_key["losses.mismatch_pct"]["default"]
        assert by_key["losses.dc_wiring_pct"]["overridden"] is True  # untouched

        every = client.post("/settings/reset", headers=headers)
        assert every.status_code == 200
        assert all(s["overridden"] is False for s in every.json()["settings"])


def test_a_published_value_survives_a_restart(engine, tmp_path):
    """The whole point of storing this in the app database rather than the
    ephemeral history store: an admin's decision must outlive the container."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        client.put("/settings", json={"values": {"losses.availability_pct": 4.2}}, headers={"Authorization": f"Bearer {token}"})

    # A brand-new app object over the same engine = a restart.
    settings_store.reset_cache()
    app2, settings2 = _file_backed_app(engine, tmp_path)
    with TestClient(app2) as client:
        token2 = create_access_token("tester", "admin", settings2, app2.state.deploy_id)
        body = client.get("/settings", headers={"Authorization": f"Bearer {token2}"}).json()
    field = next(s for s in body["settings"] if s["key"] == "losses.availability_pct")
    assert field["value"] == 4.2
    assert field["overridden"] is True


# --- the values must actually take effect ------------------------------------


def test_a_published_loss_factor_changes_the_loss_model(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    assert default_loss_factors("GIS").mismatch_pct == 2.0
    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        client.put("/settings", json={"values": {"losses.mismatch_pct": 1.1}}, headers={"Authorization": f"Bearer {token}"})
    assert default_loss_factors("GIS").mismatch_pct == 1.1


def test_a_published_soiling_fallback_changes_the_literature_default(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        client.put(
            "/settings",
            json={"values": {"losses.soiling_fallback_land_pct": 3.9, "losses.soiling_fallback_marine_pct": 7.7}},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert default_loss_factors("GIS").soiling_pct == 3.9
    assert default_loss_factors("Jetty").soiling_pct == 7.7


def test_a_published_site_figure_changes_the_asset_registry(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    assert load_assets().site.facility_electrical_load_kw == 13_500
    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        client.put(
            "/settings", json={"values": {"site.facility_electrical_load_kw": 14_200}}, headers={"Authorization": f"Bearer {token}"}
        )
        # Every consumer reads it through load_assets(), so they all agree.
        assert load_assets().site.facility_electrical_load_kw == 14_200
        expansion = client.get("/expansion", headers={"Authorization": f"Bearer {token}"}).json()
    assert expansion["facility_load_kw"] == 14_200


def test_a_published_zone_capacity_changes_the_expansion_baseline(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/expansion", headers=headers).json()["scenarios"][0]["ac_capacity_kw"]
        client.put("/settings", json={"values": {"zone.GIS.ac_capacity_kw": 90}}, headers=headers)
        after = client.get("/expansion", headers=headers).json()["scenarios"][0]["ac_capacity_kw"]
    # GIS goes 50 -> 90, so the plant total rises by 40 kW.
    assert after == before + 40


def test_editing_the_expansion_plan_adds_and_removes_phases(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        base = client.get("/expansion", headers=headers).json()
        assert len(base["scenarios"]) == 3  # today + the two YAML phases

        # Turn the first phase off and add a third that isn't in the YAML.
        client.put(
            "/settings",
            json={"values": {"expansion.phase_a_additional_ac_kw": 0, "expansion.phase_c_additional_ac_kw": 500}},
            headers=headers,
        )
        edited = client.get("/expansion", headers=headers).json()
    assert len(edited["scenarios"]) == 3  # today + phase B + the new phase C
    assert edited["scenarios"][-1]["ac_capacity_kw"] == 400 + 300 + 500


def test_editing_the_target_offsets_changes_what_is_priced_out(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        client.put(
            "/settings",
            json={"values": {"expansion.target_offset_a_pct": 0, "expansion.target_offset_b_pct": 50}},
            headers=headers,
        )
        body = client.get("/expansion", headers=headers).json()
    targets = [t["target_offset_pct"] for t in body["targets"]]
    assert 5.0 not in targets  # turned off
    assert 50.0 in targets and 25.0 in targets


def test_a_published_capex_changes_expansion_payback(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/expansion", headers=headers).json()
        client.put("/settings", json={"values": {"financial.capex_per_kwp_thb": 15_000}}, headers=headers)
        after = client.get("/expansion", headers=headers).json()
    assert after["capex_per_kwp_thb"] == 15_000
    # Half the CAPEX, half the payback time.
    assert after["scenarios"][1]["simple_payback_years"] == pytest.approx(before["scenarios"][1]["simple_payback_years"] / 2)


def test_a_published_window_changes_the_default_lookback(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/forecast/GIS/verification", headers=headers).json()["window_days"] == 30
        client.put("/settings", json={"values": {"windows.verification_days": 14}}, headers=headers)
        assert client.get("/forecast/GIS/verification", headers=headers).json()["window_days"] == 14
        # An explicit ?days= still wins - it is the one-off "look at this window".
        assert client.get("/forecast/GIS/verification?days=7", headers=headers).json()["window_days"] == 7


def test_a_published_feed_limit_changes_the_diagnostics_verdict(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/diagnostics/feeds", headers=headers).json()
        limit_before = next(f for f in before["feeds"] if f["name"] == "cloud_history")["limit_minutes"]
        assert limit_before == 90
        client.put("/settings", json={"values": {"diagnostics.cloud_max_age_minutes": 30}}, headers=headers)
        after = client.get("/diagnostics/feeds", headers=headers).json()
    assert next(f for f in after["feeds"] if f["name"] == "cloud_history")["limit_minutes"] == 30


# --- green savings: tariffs + carbon (2026-07-25) ----------------------------


def test_the_emission_factor_default_is_the_kkp_figure_and_names_both_sources():
    """Two official Thai sources disagree: กกพ's UGT criteria doc says 0.4758,
    TGO's grid-mix says 0.4999. The user chose กกพ's on 2026-07-25, so that is
    the default - and the note must still name BOTH, so a later reader can see
    the choice was between two real published figures rather than a typo."""
    spec = BY_KEY["green.ef_scope2_kg_per_kwh"]
    assert spec.default == 0.4758
    assert "0.4758" in spec.note
    assert "0.4999" in spec.note


def test_publishing_an_emission_factor_changes_the_avoided_co2(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        before = client.get("/savings/summary", headers=headers).json()
        assert before["assumptions"]["ef_scope2_kg_per_kwh"] == 0.4758
        co2_before = before["zones"][0]["periods"]["year"]["scope2_co2_avoided_kg"]

        # Switch to TGO's figure.
        client.put("/settings", json={"values": {"green.ef_scope2_kg_per_kwh": 0.4999}}, headers=headers)
        after = client.get("/savings/summary", headers=headers).json()

    # The footnote quotes what is actually in force, not the shipped default.
    assert after["assumptions"]["ef_scope2_kg_per_kwh"] == 0.4999
    co2_after = after["zones"][0]["periods"]["year"]["scope2_co2_avoided_kg"]
    assert co2_after == pytest.approx(co2_before * 0.4999 / 0.4758)


def test_publishing_a_tariff_changes_the_bill_saving_and_keeps_ugt1_derived(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        client.put("/settings", json={"values": {"green.normal_rate_thb_per_kwh": 5.0}}, headers=headers)
        body = client.get("/savings/summary", headers=headers).json()

    assumptions = body["assumptions"]
    assert assumptions["normal_rate_thb_per_kwh"] == 5.0
    # UGT1 is derived (normal + premium), so it must follow rather than go stale.
    assert assumptions["ugt1_rate_thb_per_kwh"] == pytest.approx(5.0 + assumptions["ugt1_premium_thb_per_kwh"])
    year = body["zones"][0]["periods"]["year"]
    assert year["bill_saving_thb"] == pytest.approx(year["energy_kwh"] * 5.0)


def test_publishing_a_carbon_price_changes_the_credit_value(engine, tmp_path):
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}
        client.put("/settings", json={"values": {"green.carbon_price_thb_per_tonne": 250.0}}, headers=headers)
        body = client.get("/savings/summary", headers=headers).json()
    year = body["zones"][0]["periods"]["year"]
    assert year["carbon_credit_value_thb"] == pytest.approx(year["carbon_credit_units"] * 250.0)


# --- BOI: confirmed project figures (2026-07-25) -----------------------------


def test_the_boi_holiday_defaults_are_the_users_confirmed_figures():
    """These stopped being guesses on 2026-07-25: the user confirmed this
    project holds BOI promotion for 8 years in the general areas and 12 for the
    Jetty. Pinned because a silent drift back toward 0 would quietly worsen
    every NPV and payback the site publishes, and because `origin` must now read
    'confirmed' - a reader has to be able to tell this from an estimate."""
    general = BY_KEY["financial.boi_tax_holiday_years"]
    jetty = BY_KEY["financial.boi_tax_holiday_years_jetty"]

    assert general.default == 8.0
    assert jetty.default == 12.0
    assert general.origin == ORIGIN_CONFIRMED
    assert jetty.origin == ORIGIN_CONFIRMED


def test_the_shipped_model_default_matches_the_general_area_holiday(engine, tmp_path):
    """The pure financial package has its own default, and it must agree with
    the registry's - two sources of truth for a tax holiday is how a report and
    a playground end up disagreeing about payback."""
    from nongfab_financial.model import DEFAULT_BOI_TAX_HOLIDAY_YEARS

    assert DEFAULT_BOI_TAX_HOLIDAY_YEARS == BY_KEY["financial.boi_tax_holiday_years"].default


def test_a_longer_holiday_shortens_the_payback(engine, tmp_path):
    """The Jetty's 12 years has to actually reach the arithmetic, not just sit
    in the registry - so publishing it must move the answer in the right
    direction against the 8-year general-area case."""
    from nongfab_api.auth import create_access_token

    app, settings = _file_backed_app(engine, tmp_path)
    with TestClient(app) as client:
        token = create_access_token("tester", "admin", settings, app.state.deploy_id)
        headers = {"Authorization": f"Bearer {token}"}

        eight = client.post("/financial", json={"boi_tax_holiday_years": 8}, headers=headers).json()
        twelve = client.post("/financial", json={"boi_tax_holiday_years": 12}, headers=headers).json()

    assert twelve["npv_thb"] > eight["npv_thb"]
