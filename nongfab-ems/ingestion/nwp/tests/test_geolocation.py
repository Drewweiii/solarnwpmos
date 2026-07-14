from nwp_ingestion.geolocation import nong_fab_fetch_bbox


def test_nong_fab_fetch_bbox_pads_beyond_plant_bbox():
    tight = nong_fab_fetch_bbox(padding_deg=0.0)
    padded = nong_fab_fetch_bbox(padding_deg=0.3)

    assert padded.lat_min < tight.lat_min
    assert padded.lat_max > tight.lat_max
    assert padded.lon_min < tight.lon_min
    assert padded.lon_max > tight.lon_max


def test_nong_fab_fetch_bbox_covers_nominal_site_center():
    bbox = nong_fab_fetch_bbox(padding_deg=0.3)
    # Nong Fab nominal center from config/assets.yaml
    assert bbox.lat_min < 12.71 < bbox.lat_max
    assert bbox.lon_min < 101.15 < bbox.lon_max
