import numpy as np
import pandas as pd
import pytest

from pydatamatch.match import (
    detect_temporal_resolution,
    match_data,
    standardize_time_columns,
)


def grid(year, month, sst):
    """A 2x2 source grid for one month, with a known value per cell."""
    return pd.DataFrame({
        "x": [-70.0, -69.0, -70.0, -69.0],
        "y": [42.0, 42.0, 43.0, 43.0],
        "SST": sst,
        "YEAR": year,
        "MONTH": month,
    })


def test_nearest_cell_in_the_same_period():
    source = pd.concat(
        [grid(2015, 1, [1.0, 2.0, 3.0, 4.0]), grid(2015, 2, [5.0, 6.0, 7.0, 8.0])],
        ignore_index=True,
    )
    source.attrs["step"] = "month"
    dat = pd.DataFrame({
        "lon": [-69.9, -69.1], "lat": [42.1, 42.9],
        "year": [2015, 2015], "month": [1, 2],
    })
    out = match_data(dat, source)
    # Nearest to (-70, 42) in January is 1.0; nearest to (-69, 43) in February is 8.0.
    assert out["SST"].tolist() == [1.0, 8.0]


def test_row_count_and_order_preserved_with_gaps():
    source = grid(2015, 1, [1.0, 2.0, 3.0, 4.0])
    source.attrs["step"] = "month"
    dat = pd.DataFrame({
        "lon": [-70.0, -70.0, -70.0], "lat": [42.0, 42.0, 42.0],
        "year": [2015, 2016, 2015], "month": [2, 1, 1],
    })
    with pytest.warns(UserWarning, match="2 period"):
        out = match_data(dat, source)
    assert len(out) == 3
    # Uncovered periods give NaN, in place, rather than dropped rows.
    assert np.isnan(out["SST"].iloc[0])
    assert np.isnan(out["SST"].iloc[1])
    assert out["SST"].iloc[2] == 1.0


def test_colliding_column_suffixed_not_overwritten():
    source = grid(2015, 1, [1.0, 2.0, 3.0, 4.0])
    source.attrs["step"] = "month"
    dat = pd.DataFrame({
        "lon": [-70.0], "lat": [42.0], "year": [2015], "month": [1],
        "SST": [99.0],  # the caller's own SST column
    })
    out = match_data(dat, source)
    assert out["SST"].iloc[0] == 99.0
    assert out["SST.matched"].iloc[0] == 1.0


def test_provenance_column_recorded():
    source = grid(2015, 1, [1.0, 2.0, 3.0, 4.0])
    source.attrs["step"] = "month"
    source.attrs["source"] = "copernicus:cmems_mod_glo_phy_my_0.083deg_P1M-m"
    dat = pd.DataFrame({"lon": [-70.0], "lat": [42.0], "year": [2015], "month": [1]})
    out = match_data(dat, source)
    assert out["SST_source"].iloc[0].startswith("copernicus:")


def test_daily_matching_needs_a_day_column():
    source = grid(2015, 1, [1.0, 2.0, 3.0, 4.0])
    source["DAY"] = 5
    source.attrs["step"] = "day"
    dat = pd.DataFrame({"lon": [-70.0], "lat": [42.0], "year": [2015], "month": [1]})
    with pytest.raises(ValueError, match="'DAY'"):
        match_data(dat, source)


def test_detects_daily_from_time_steps():
    a = grid(2015, 1, [1.0, 2.0, 3.0, 4.0])
    a["DAY"] = 1
    b = grid(2015, 1, [1.0, 2.0, 3.0, 4.0])
    b["DAY"] = 2
    assert detect_temporal_resolution(pd.concat([a, b])) == "day"


def test_detects_monthly_from_time_steps():
    both = pd.concat([grid(2015, 1, [1.0] * 4), grid(2015, 2, [1.0] * 4)])
    assert detect_temporal_resolution(both) == "month"


def test_recorded_step_beats_inference():
    # One date per month looks monthly by inspection; the recorded step wins.
    one = grid(2015, 1, [1.0] * 4)
    one["DAY"] = 15
    one.attrs["step"] = "day"
    assert detect_temporal_resolution(one) == "day"


def test_day_of_year_columns_never_used():
    dat = pd.DataFrame({"yearday": [100], "month": [4]})
    with pytest.raises(ValueError, match="yearday"):
        standardize_time_columns(dat, ["YEAR", "MONTH"])


def test_prefix_match_with_exact_tiebreak():
    dat = pd.DataFrame({"Year": [2015], "month_utc": [4], "day": [2], "day_night": ["d"]})
    out = standardize_time_columns(dat, ["YEAR", "MONTH", "DAY"])
    assert {"YEAR", "MONTH", "DAY", "day_night"} <= set(out.columns)
    assert out["DAY"].iloc[0] == 2
