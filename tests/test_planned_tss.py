import pytest

from lockedin.agenda.parts import parts, target_series, tss_estimate
from lockedin.agenda.zwo import ZwiftWorkout


def plan(*blocks):
    return parts(ZwiftWorkout(blocks=list(blocks)), 250)


def test_steady_hour_at_75_percent():
    assert tss_estimate(plan({"type": "steady", "duration_s": 3600, "power": 0.75})) == 56


def test_intervals_count_their_normalized_power():
    # 3 × (5 min at 120 %, 5 min at 50 %): time × fraction² said 42; NP (≈ 101 % FTP) over 30 min says ~51
    ps = plan({"type": "intervals", "repeat": 3, "on_s": 300, "off_s": 300, "on_power": 1.2, "off_power": 0.5})
    assert tss_estimate(ps) == pytest.approx(51, abs=1)


def test_ramps_are_interpolated_second_by_second():
    s = target_series(plan({"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.7}))
    assert len(s) == 600 and s[0] == pytest.approx(0.5, abs=0.001) and s[-1] == pytest.approx(0.7, abs=0.001)


def test_free_ride_is_assumed_easy():
    assert tss_estimate(plan({"type": "free", "duration_s": 3600})) == 25  # 50 % FTP for an hour


def test_too_short_to_say():
    assert tss_estimate(plan({"type": "steady", "duration_s": 20, "power": 0.6})) == 0
