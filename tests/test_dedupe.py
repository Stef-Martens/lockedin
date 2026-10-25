import pytest
from conftest import get_activity, read, stream, superseded_by

from lockedin.fit.importer import import_fit


def imp(conn, names):
    return {n: import_fit(conn, read(n), n, None).activity_id for n in names}


@pytest.mark.parametrize("order", [("zwift_ride.fit", "watch_indoor_cycle.fit"),
                                   ("watch_indoor_cycle.fit", "zwift_ride.fit")])
def test_watch_superseded_by_zwift(conn, order):
    ids = imp(conn, order)
    assert superseded_by(conn, ids["watch_indoor_cycle.fit"]) == ids["zwift_ride.fit"]
    assert superseded_by(conn, ids["zwift_ride.fit"]) is None


def test_zwift_hr_kept_when_present(conn):
    ids = imp(conn, ["zwift_ride.fit", "watch_indoor_cycle.fit"])
    ride = get_activity(conn, ids["zwift_ride.fit"])
    assert ride.avg_hr == 145 and ride.hr_merged_from is None


@pytest.mark.parametrize("order", [("zwift_ride_no_hr.fit", "watch_indoor_cycle.fit"),
                                   ("watch_indoor_cycle.fit", "zwift_ride_no_hr.fit")])
def test_hr_merged_when_zwift_has_no_hr(conn, order):
    ids = imp(conn, order)
    ride = get_activity(conn, ids["zwift_ride_no_hr.fit"])
    assert ride.hr_merged_from == ids["watch_indoor_cycle.fit"]
    assert ride.avg_hr is not None and ride.max_hr is not None
    hr = stream(conn, ride.id).hr
    assert sum(h is not None for h in hr) > 3000
    # Watch HR ramps 128→162 over 3700 s starting 2 min before the ride; ride second 0 ≈ watch second 120
    assert hr[0] == pytest.approx(129, abs=1)


def test_non_overlapping_untouched(conn):
    ids = imp(conn, ["zwift_ride.fit", "watch_run.fit"])
    assert superseded_by(conn, ids["watch_run.fit"]) is None


def test_small_overlap_is_not_a_duplicate(conn):
    # Walk 12:00–12:20 vs strength 17:05–17:55 on the same day: no overlap at all
    ids = imp(conn, ["watch_walk.fit", "watch_strength.fit"])
    assert superseded_by(conn, ids["watch_walk.fit"]) is None
