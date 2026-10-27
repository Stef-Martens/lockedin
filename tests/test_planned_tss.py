import pytest

from lockedin.agenda.parts import parts, target_series, tss_estimate
from lockedin.agenda.zwo import ZwiftWorkout
from lockedin.forecast.ahead import PLANNED_MIN, UNMEASURED_IF, ZONE_IF, planned_load


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


def run(targets):
    return {"sport": "run", "zwift": None, "targets": targets}


def load(seconds, intensity):
    return seconds / 3600 * intensity ** 2 * 100


def test_stepped_run_uses_step_time():
    steps = {
        "warmup": {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
        "blocks": [{"repeat": 3, "steps": [
            {"kind": "work", "goal": {"time_s": 600}, "target": {"hr_zone": 4}},
            {"kind": "recovery", "goal": {"time_s": 120}},
        ]}],
        "cooldown": {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
    }
    expected = load(1200, ZONE_IF[2]) + 3 * (load(600, ZONE_IF[4]) + load(120, ZONE_IF[1]))
    assert planned_load(run({"steps": steps})) == pytest.approx(expected)


def test_tempo_harder_than_easy_same_length():
    steps = {
        "warmup": {"goal": {"time_s": 600}},
        "blocks": [{"repeat": 4, "steps": [
            {"kind": "work", "goal": {"time_s": 300}, "target": {"pace_low": 270, "pace_high": 280}},
            {"kind": "recovery", "goal": {"time_s": 120}},
        ]}],
        "cooldown": {"goal": {"time_s": 600}},
    }
    total = 600 + 4 * (300 + 120) + 600
    assert planned_load(run({"steps": steps})) > planned_load(run({"duration_s": total}))


def test_distance_steps_use_their_pace():
    steps = {"blocks": [{"repeat": 5, "steps": [
        {"kind": "work", "goal": {"distance_m": 1000}, "target": {"pace_low": 240, "pace_high": 250}},
    ]}]}
    assert planned_load(run({"steps": steps})) == pytest.approx(5 * load(245, ZONE_IF[4]))


def test_distance_step_without_pace_uses_the_run_summary_pace():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 2000}}]}]}
    targets = {"steps": steps, "pace_low": 300, "pace_high": 320}
    assert planned_load(run(targets)) == pytest.approx(load(2 * 310, UNMEASURED_IF))


def test_steps_adding_up_to_no_time_count_as_a_plain_run():
    distance_only = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 2000}}]}]}
    all_open = {"blocks": [{"repeat": 6, "steps": [{"kind": "work", "goal": {"open": True}}]}]}
    plain = load(PLANNED_MIN["run"] * 60, UNMEASURED_IF)
    assert planned_load(run({"steps": distance_only})) == pytest.approx(plain)
    assert planned_load(run({"steps": all_open})) == pytest.approx(plain)


def test_open_steps_are_skipped():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}}]}],
             "cooldown": {"goal": {"open": True}}}
    assert planned_load(run({"steps": steps})) == pytest.approx(load(600, UNMEASURED_IF))
