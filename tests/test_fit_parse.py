from datetime import UTC, datetime

import pytest
from conftest import read

from lockedin.fit.parse import FitParseError, parse_fit


def test_parse_zwift_ride():
    f = parse_fit(read("zwift_ride.fit"))
    assert (f.sport, f.manufacturer, f.duration_s) == ("bike", "zwift", 3600)
    assert f.sub_type == "cycling/virtual_activity"
    assert f.start_at == datetime(2026, 10, 20, 17, 0, tzinfo=UTC)
    assert f.end_at == datetime(2026, 10, 20, 18, 0, tzinfo=UTC)
    assert f.avg_power == pytest.approx(200, abs=2) and f.max_power == 250
    assert (f.avg_hr, f.max_hr, f.avg_cadence) == (145, 160, 85)
    assert f.distance_m == pytest.approx(30000, rel=0.01)
    assert len(f.streams.power) == 3600 and f.streams.t_offset[:3] == [0, 1, 2]
    assert f.streams.hr[0] == 130


def test_parse_ride_without_hr():
    f = parse_fit(read("zwift_ride_no_hr.fit"))
    assert f.avg_hr is None and set(f.streams.hr) == {None}


def test_parse_run():
    f = parse_fit(read("watch_run.fit"))
    assert (f.sport, f.manufacturer) == ("run", "development")
    assert f.distance_m == pytest.approx(8000, rel=0.01) and f.duration_s == 2700


def test_parse_pool_swim():
    f = parse_fit(read("watch_pool_swim.fit"))
    assert (f.sport, f.pool_length_m, f.swim_lengths, f.swim_strokes) == ("swim", 25.0, 40, 720)


def test_parse_walk_and_strength_subtypes():
    assert parse_fit(read("watch_walk.fit")).sub_type.startswith("walking")
    s = parse_fit(read("watch_strength.fit"))
    assert s.sport == "other" and s.sub_type.startswith("training")


def test_parse_corrupt_raises():
    with pytest.raises(FitParseError):
        parse_fit(read("corrupt.fit"))


def test_parse_garbage_raises():
    with pytest.raises(FitParseError):
        parse_fit(b"not a fit file at all")
