"""GET /ar/{zone}.usdz (2026-07-26, project T) - AR for iOS via AR Quick Look.

The format rules here are not stylistic: get them wrong and Safari downloads a
file instead of opening AR, which looks from the outside like "AR is broken on
iPhone". These tests pin the ones that fail silently.
"""

from __future__ import annotations

import struct
import zipfile

from fastapi.testclient import TestClient

from nongfab_api.usdz import PanelPlacement, build_usda, build_usdz

PANELS = [
    PanelPlacement(east_m=0.0, north_m=0.0, width_m=2.3, slant_height_m=1.1),
    PanelPlacement(east_m=120.0, north_m=45.0, width_m=2.3, slant_height_m=1.1),
]


def test_usdz_requires_a_token(app):
    with TestClient(app) as client:
        # No Authorization header is possible here, so the query token is the
        # only credential - its absence must still be a rejection.
        assert client.get("/ar/GIS.usdz").status_code == 422
        assert client.get("/ar/GIS.usdz?token=nonsense").status_code == 401


def test_serves_the_apple_media_type(app, token_factory):
    """`application/zip` makes Safari download the file rather than open AR."""
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(f"/ar/GIS.usdz?token={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("model/vnd.usdz+zip")


def test_unknown_zone_names_the_real_ones(app, token_factory):
    token = token_factory("viewer")
    with TestClient(app) as client:
        resp = client.get(f"/ar/Atlantis.usdz?token={token}")
    assert resp.status_code == 404
    assert "GIS" in resp.json()["detail"]


def test_every_payload_starts_64_byte_aligned():
    """The rule that decides whether Quick Look opens the file at all: it
    memory-maps the archive, so a misaligned entry is rejected outright."""
    model = build_usdz(PANELS, tilt_deg=15.0, azimuth_deg=180.0, zone="GIS")
    with zipfile.ZipFile(__import__("io").BytesIO(model.data)) as zf:
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED, "USDZ entries must never be deflated"
            zf.fp.seek(info.header_offset)
            header = zf.fp.read(30)
            name_len, extra_len = struct.unpack("<HH", header[26:30])
            data_offset = info.header_offset + 30 + name_len + extra_len
            assert data_offset % 64 == 0, f"{info.filename} payload at {data_offset} is not 64-byte aligned"


def test_the_root_layer_is_the_first_entry():
    # Readers take the first entry as the layer to open.
    model = build_usdz(PANELS, tilt_deg=15.0, azimuth_deg=180.0, zone="GIS")
    with zipfile.ZipFile(__import__("io").BytesIO(model.data)) as zf:
        assert zf.namelist()[0].endswith(".usda")


def test_geometry_is_metres_y_up_with_one_quad_per_panel():
    usda = build_usda(PANELS, tilt_deg=15.0, azimuth_deg=180.0, zone="GIS", scale=0.005)
    assert "metersPerUnit = 1" in usda
    assert 'upAxis = "Y"' in usda
    assert 'defaultPrim = "NongFab"' in usda
    # Two panels, one quad each - merged into a single mesh rather than two prims.
    assert "int[] faceVertexCounts = [4, 4]" in usda
    assert usda.count("def Mesh") == 2  # panels + ground pad


def test_a_tilted_panel_is_actually_tilted():
    """A flat model would look plausible and be wrong. The four corners of a
    tilted panel must not share one height."""
    flat = build_usda(PANELS[:1], tilt_deg=0.0, azimuth_deg=180.0, zone="GIS", scale=1.0)
    tilted = build_usda(PANELS[:1], tilt_deg=25.0, azimuth_deg=180.0, zone="GIS", scale=1.0)
    assert flat != tilted


def test_the_model_is_shrunk_to_table_size_and_says_by_how_much():
    model = build_usdz(PANELS, tilt_deg=15.0, azimuth_deg=180.0, zone="GIS")
    # 120 m of array onto a 0.6 m table.
    assert 0 < model.scale < 0.01
    assert model.scale_ratio_label().startswith("1 : ")
    # An AR model with no stated scale invites reading its size as the real one,
    # so the scale travels with the file as well as in the UI.
    assert "Scaled to" in model.data.decode("utf-8", errors="ignore")


def test_no_panels_still_produces_a_valid_package():
    model = build_usdz([], tilt_deg=0.0, azimuth_deg=180.0, zone="GIS")
    with zipfile.ZipFile(__import__("io").BytesIO(model.data)) as zf:
        assert zf.namelist()
    assert model.scale == 1.0
