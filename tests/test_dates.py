import datetime as dt

import pytest

from pydatamatch._dates import parse_dates, stop_if_future


def test_accepts_compact_iso_and_date_objects_mixed():
    parsed = parse_dates(["20150402", "2015-05-17", dt.date(2015, 6, 23)])
    assert parsed == [dt.date(2015, 4, 2), dt.date(2015, 5, 17), dt.date(2015, 6, 23)]


def test_sorted_and_deduplicated():
    parsed = parse_dates(["20150517", "20150402", "2015-04-02"])
    assert parsed == [dt.date(2015, 4, 2), dt.date(2015, 5, 17)]


def test_single_value_accepted():
    assert parse_dates("20150402") == [dt.date(2015, 4, 2)]
    assert parse_dates(20150402) == [dt.date(2015, 4, 2)]


def test_impossible_date_is_an_error_naming_it():
    with pytest.raises(ValueError, match="20150230"):
        parse_dates(["20150402", "20150230"])


def test_empty_is_an_error():
    with pytest.raises(ValueError, match="empty"):
        parse_dates([])


def test_future_dates_refused():
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    with pytest.raises(ValueError, match="not happened yet"):
        stop_if_future([tomorrow], "Copernicus")


def test_forecast_horizon_allows_near_future():
    soon = dt.date.today() + dt.timedelta(days=5)
    stop_if_future([soon], "Copernicus", ahead=10)
    beyond = dt.date.today() + dt.timedelta(days=30)
    with pytest.raises(ValueError):
        stop_if_future([beyond], "Copernicus", ahead=10)
