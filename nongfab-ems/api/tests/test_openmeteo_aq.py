from datetime import timezone

from nongfab_api.openmeteo_aq import SOURCE_NAME, AerosolPoint, parse_aerosol_response


def _payload():
    return {
        "hourly": {
            "time": ["2026-07-24T00:00", "2026-07-24T01:00", "2026-07-24T02:00"],
            "aerosol_optical_depth": [0.21, 0.25, None],
            "dust": [8.0, 9.5, None],
            "pm2_5": [18.0, 22.0, None],
            "pm10": [30.0, 35.0, None],
        }
    }


def test_parse_maps_variables_and_keeps_utc():
    points = parse_aerosol_response(_payload())
    # The all-null 3rd hour is dropped; the two real hours are kept, oldest-first.
    assert len(points) == 2
    assert isinstance(points[0], AerosolPoint)
    assert points[0].aod_550nm == 0.21
    assert points[0].dust == 8.0
    assert points[0].pm2_5 == 18.0
    assert points[0].pm10 == 30.0
    assert points[0].source == SOURCE_NAME
    assert points[0].valid_time.tzinfo == timezone.utc
    assert points[0].valid_time.hour == 0
    assert points[1].valid_time.hour == 1


def test_parse_keeps_partial_rows_and_never_fabricates():
    payload = {
        "hourly": {
            "time": ["2026-07-24T00:00"],
            "aerosol_optical_depth": [0.3],
            "dust": [None],
            "pm2_5": [None],
            "pm10": [40.0],
        }
    }
    points = parse_aerosol_response(payload)
    assert len(points) == 1
    assert points[0].aod_550nm == 0.3
    assert points[0].dust is None  # missing stays None, not 0
    assert points[0].pm2_5 is None
    assert points[0].pm10 == 40.0


def test_parse_empty_payload_returns_nothing():
    assert parse_aerosol_response({}) == []
    assert parse_aerosol_response({"hourly": {}}) == []
