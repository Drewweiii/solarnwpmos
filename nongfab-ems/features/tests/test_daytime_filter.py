import pandas as pd
import pytest

from nongfab_features.daytime_filter import filter_daytime


def test_filter_daytime_drops_high_zenith_rows():
    df = pd.DataFrame({"zenith_deg": [10.0, 84.9, 85.0, 90.0, 170.0], "value": [1, 2, 3, 4, 5]})
    result = filter_daytime(df)

    assert list(result["value"]) == [1, 2]  # only zenith < 85 survives


def test_filter_daytime_custom_threshold():
    df = pd.DataFrame({"zenith_deg": [10.0, 50.0, 90.0], "value": [1, 2, 3]})
    result = filter_daytime(df, max_zenith_deg=60.0)
    assert list(result["value"]) == [1, 2]


def test_filter_daytime_raises_on_missing_column():
    df = pd.DataFrame({"value": [1, 2, 3]})
    with pytest.raises(KeyError):
        filter_daytime(df)
