import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from focus_helpers import add_gym, add_session
from sqlalchemy import text
from test_run_steps import TEMPO

from lockedin import timeoff
from lockedin.agenda.store import ItemIn, create
from lockedin.focus.zones import hr_ranges
from lockedin.timeoff import Restriction, TimeOffIn
from lockedin.verdict.facts import MATCHED_BY, facts, step_results

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=UTC)
START = datetime(2026, 10, 29, 7, tzinfo=UTC)
BENCH = "Bench Press (Barbell)"
SWEET_SPOT = {"blocks": [
    {"type": "warmup", "duration_s": 600, "from_power": 0.5, "to_power": 0.75},
    {"type": "intervals", "repeat": 3, "on_s": 600, "off_s": 300, "on_power": 0.9, "off_power": 0.55},
    {"type": "cooldown", "duration_s": 600, "from_power": 0.65, "to_power": 0.45},
]}
Z = {1: (114, 137), 2: (137, 156), 3: (156, 165), 4: (165, 175), 5: (175, 190)}  # max HR 190


def add(conn, **fields):
    return create(conn, NOW, ItemIn(**fields), "coach")["id"]


def stream(*stretches):
    """1 sample per second; each stretch is (seconds, m/s, HR). Sample i closes the second before it."""
    t, speed, hr, dist = [0], [stretches[0][1]], [stretches[0][2]], [0.0]
    for seconds, v, h in stretches:
        for _ in range(seconds):
            t.append(t[-1] + 1)
            speed.append(v)
            hr.append(h)
            dist.append(dist[-1] + v)
    return SimpleNamespace(t_offset=t, speed=speed, hr=hr, distance=dist)


def tempo_stream():
    return stream((600, 2.5, 140), (300, 3.0, 160), (120, 2.0, 130), (300, 2.5, 165), (120, 2.0, 135),
                  (300, 3.0, 162), (120, 2.0, 136), (300, 3.0, 163), (120, 2.0, 137), (300, 2.0, 125))


def save_stream(conn, aid, s):
    conn.execute(text(
        "insert into activity_streams (activity_id, t_offset, hr, speed, distance) values "
        "(:i, cast(:t as integer[]), cast(:h as smallint[]), cast(:s as real[]), cast(:d as real[]))"
    ), {"i": aid, "t": s.t_offset, "h": s.hr, "s": s.speed, "d": s.distance})


def add_run(conn, s=None, start=START, **fields):
    s = s or tempo_stream()
    aid = add_session(conn, "run", start, s.t_offset[-1], distance_m=s.distance[-1], avg_hr=150, **fields)
    save_stream(conn, aid, s)
    return aid


def lists_in(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from lists_in(v)
    elif isinstance(value, list):
        yield value
        for v in value:
            yield from lists_in(v)


# ---- step_results


def test_steps_by_time():
    rows = step_results(TEMPO, tempo_stream(), Z)
    work = {"pace_low": 330, "pace_high": 350}
    assert [r["kind"] for r in rows] == ["warmup"] + ["work", "recovery"] * 4
    assert [r["repeat"] for r in rows] == [None, 1, 1, 2, 2, 3, 3, 4, 4]
    assert rows[:4] == [
        {"kind": "warmup", "repeat": None, "goal": {"time_s": 600}, "target": {"hr_zone": 2}, "seconds": 600,
         "metres": 1500, "pace_s_per_km": 400, "avg_hr": 140, "in_target": True},
        {"kind": "work", "repeat": 1, "goal": {"time_s": 300}, "target": work, "seconds": 300,
         "metres": 900, "pace_s_per_km": 333, "avg_hr": 160, "in_target": True},
        {"kind": "recovery", "repeat": 1, "goal": {"time_s": 120}, "target": None, "seconds": 120,
         "metres": 240, "pace_s_per_km": 500, "avg_hr": 130, "in_target": None},
        {"kind": "work", "repeat": 2, "goal": {"time_s": 300}, "target": work, "seconds": 300,
         "metres": 750, "pace_s_per_km": 400, "avg_hr": 165, "in_target": False},
    ]


def test_zone_target_is_judged_by_average_hr():
    steps = {"warmup": {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
             "blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"open": True}}]}]}
    assert step_results(steps, stream((600, 2.5, 137)), Z)[0]["in_target"] is True
    assert step_results(steps, stream((600, 2.5, 157)), Z)[0]["in_target"] is False


def test_no_data_leaves_in_target_null():
    steps = {"warmup": {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
             "blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"open": True}}]}]}
    s = stream((600, 2.5, 140))
    assert step_results(steps, s)[0]["in_target"] is None  # max HR not known
    s.hr = None
    row = step_results(steps, s, Z)[0]
    assert row["avg_hr"] is None and row["in_target"] is None and row["seconds"] == 600


def test_dropped_hr_samples_do_not_pull_the_average_down():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 100}}]}]}
    s = stream((100, 2.5, 150))
    s.hr[1:21] = [None] * 10 + [0] * 10
    assert step_results(steps, s)[0]["avg_hr"] == 150


def test_steps_by_distance():
    steps = {"warmup": {"goal": {"distance_m": 1000}},
             "blocks": [{"repeat": 2, "steps": [
                 {"kind": "work", "goal": {"distance_m": 400}, "target": {"pace_low": 240, "pace_high": 260}},
                 {"kind": "recovery", "goal": {"time_s": 60}}]}]}
    s = stream((200, 2.5, 130), (125, 4.0, 140), (100, 4.0, 170), (60, 2.0, 120), (80, 5.0, 175), (60, 2.0, 121))
    rows = step_results(steps, s)
    assert [(r["seconds"], r["metres"], r["pace_s_per_km"]) for r in rows] == [
        (325, 1000, 325), (100, 400, 250), (60, 120, 500), (80, 400, 200), (60, 120, 500)]
    assert [r["in_target"] for r in rows] == [None, True, None, False, None]


def test_boundary_between_samples_is_interpolated():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 1000}},
                                                {"kind": "recovery", "goal": {"time_s": 60}}]}]}
    rows = step_results(steps, stream((500, 3.0, 150)))
    assert (rows[0]["seconds"], rows[0]["metres"]) == (333, 1000)
    assert (rows[1]["seconds"], rows[1]["metres"]) == (60, 180)


WORK_THEN_JOG = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}},
                                                    {"kind": "recovery", "goal": {"time_s": 120}}]}]}


def test_long_stop_with_samples_gets_no_results_on_time_goals():
    """With auto-pause off the watch's step clock runs on through it, so later windows would be off by its length."""
    s = stream((300, 3.0, 160), (31, 0.0, 100), (300, 3.0, 160), (120, 2.0, 130))
    assert step_results(WORK_THEN_JOG, s) is None


def test_short_stops_with_samples_add_up():
    s = stream((100, 3.0, 160), (16, 0.0, 100), (100, 3.0, 160), (16, 0.0, 100), (400, 3.0, 160), (120, 2.0, 130))
    assert step_results(WORK_THEN_JOG, s) is None


def test_short_stop_with_samples_does_not_shift_steps():
    s = stream((300, 3.0, 160), (30, 0.0, 100), (300, 3.0, 160), (120, 2.0, 130))
    rows = step_results(WORK_THEN_JOG, s)
    assert [(r["seconds"], r["metres"], r["avg_hr"]) for r in rows] == [(600, 1800, 160), (120, 240, 130)]


def test_long_stop_after_the_matched_steps_is_fine():
    s = stream((600, 3.0, 160), (120, 2.0, 130), (200, 0.0, 100), (300, 2.0, 125))
    rows = step_results({**WORK_THEN_JOG, "cooldown": {"goal": {"open": True}}}, s)
    assert [(r["seconds"], r["metres"]) for r in rows] == [(600, 1800), (120, 240)]


def test_long_stop_with_samples_does_not_touch_distance_goals():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 1800}},
                                                {"kind": "recovery", "goal": {"distance_m": 240}}]}]}
    s = stream((300, 3.0, 160), (200, 0.0, 100), (300, 3.0, 160), (120, 2.0, 130))
    rows = step_results(steps, s)
    assert [(r["seconds"], r["metres"], r["avg_hr"]) for r in rows] == [(600, 1800, 160), (120, 240, 130)]


def three_blocks():
    return stream((600, 3.0, 160), (300, 2.0, 130), (600, 3.0, 160))


THREE_BLOCKS = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}},
                                                   {"kind": "recovery", "goal": {"time_s": 300}},
                                                   {"kind": "work", "goal": {"time_s": 600}}]}]}


def test_clean_three_blocks():
    rows = step_results(THREE_BLOCKS, three_blocks())
    assert [(r["seconds"], r["metres"], r["pace_s_per_km"]) for r in rows] == [(600, 1800, 333), (300, 600, 500), (600, 1800, 333)]


def test_gps_dropout_without_distance_or_speed_gets_no_results():
    """Was (600, 2040, 294), (300, 720, 417), (480, 1440, 333): the gap counted as stopped, the metres arrived in one jump."""
    s = three_blocks()
    for i in range(300, 420):
        s.distance[i] = s.speed[i] = None
    assert step_results(THREE_BLOCKS, s) is None


def test_gps_dropout_with_speed_zero_gets_no_results():
    s = three_blocks()
    for i in range(300, 420):
        s.distance[i], s.speed[i] = None, 0.0
    assert step_results(THREE_BLOCKS, s) is None


def test_samples_missing_with_slow_looking_metres_get_no_results():
    """Was (600, 2200, 273), (300, 600, 500), (600, 1800, 333): 400 m over 900 s reads as under 0.5 m/s, so as stopped."""
    s = stream((300, 3.0, 160), (1, 0.0, 160), (300, 3.0, 160), (300, 2.0, 130), (600, 3.0, 160))
    s.distance = s.distance[:301] + [d + 400 for d in s.distance[301:]]
    s.t_offset = s.t_offset[:301] + [t + 899 for t in s.t_offset[301:]]
    assert step_results(THREE_BLOCKS, s) is None


def test_metres_jumping_ahead_on_distance_goals_get_no_results():
    """Was (50 s, 300 m, 167), (17 s, 300 m, 56): 400 m in no moving time."""
    steps = {"blocks": [{"repeat": 2, "steps": [{"kind": "work", "goal": {"distance_m": 300}}]}]}
    s = stream((50, 3.0, 160), (1, 0.0, 160), (200, 3.0, 160))
    assert len(step_results(steps, s)) == 2
    s.distance = s.distance[:51] + [d + 400 for d in s.distance[51:]]
    s.t_offset = s.t_offset[:51] + [t + 899 for t in s.t_offset[51:]]
    assert step_results(steps, s) is None


def test_metres_jumping_after_the_matched_steps_are_fine():
    s = stream((600, 3.0, 160), (120, 2.0, 130), (1, 0.0, 130), (300, 2.0, 125))
    s.distance = s.distance[:722] + [d + 400 for d in s.distance[722:]]
    s.t_offset = s.t_offset[:722] + [t + 899 for t in s.t_offset[722:]]
    rows = step_results({**WORK_THEN_JOG, "cooldown": {"goal": {"open": True}}}, s)
    assert [(r["seconds"], r["metres"]) for r in rows] == [(600, 1800), (120, 240)]


def test_gps_drift_during_an_auto_pause_is_fine():
    s = stream((300, 3.0, 160), (1, 0.0, 100), (300, 3.0, 160), (120, 2.0, 130))
    s.distance = s.distance[:301] + [d + 20 for d in s.distance[301:]]
    s.t_offset = s.t_offset[:301] + [t + 500 for t in s.t_offset[301:]]
    rows = step_results(WORK_THEN_JOG, s)
    assert [(r["seconds"], r["metres"]) for r in rows] == [(600, 1820), (120, 240)]


def test_metres_in_no_moving_time_give_no_pace():
    """Never a pace of 0."""
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 20}}]}]}
    s = SimpleNamespace(t_offset=[0, 100], speed=None, hr=None, distance=[0.0, 25.0])
    row = step_results(steps, s)[0]
    assert (row["seconds"], row["metres"], row["pace_s_per_km"], row["in_target"]) == (0, 20, None, None)


def test_auto_pause_without_samples_does_not_shift_steps():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}},
                                                {"kind": "recovery", "goal": {"time_s": 120}}]}]}
    s = stream((300, 3.0, 160), (1, 0.0, 100), (300, 3.0, 160), (120, 2.0, 130))
    s.t_offset = s.t_offset[:301] + [t + 500 for t in s.t_offset[301:]]  # the first sample back is where it stopped
    rows = step_results(steps, s)
    assert [(r["seconds"], r["metres"], r["avg_hr"]) for r in rows] == [(600, 1800, 160), (120, 240, 130)]


def test_open_goal_stops_matching():
    steps = {"warmup": {"goal": {"time_s": 300}},
             "blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"open": True}},
                                                {"kind": "recovery", "goal": {"time_s": 60}}]}],
             "cooldown": {"goal": {"time_s": 300}}}
    rows = step_results(steps, stream((300, 2.5, 130), (900, 3.0, 160)))
    assert [r["kind"] for r in rows] == ["warmup"]


def test_nothing_before_the_open_step_gives_no_results():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"open": True}},
                                                {"kind": "recovery", "goal": {"time_s": 60}}]}]}
    assert step_results(steps, stream((900, 3.0, 160))) is None


def test_free_run_gets_no_results():
    planned_before_open = 600 + 4 * 420  # TEMPO: 2280 s
    assert step_results(TEMPO, stream((int(planned_before_open * 0.89), 2.5, 150))) is None
    assert step_results(TEMPO, stream((int(planned_before_open * 0.91), 2.5, 150))) is not None


def test_coverage_is_judged_on_metres_for_distance_goals():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 10000}}]}]}
    assert step_results(steps, stream((3560, 2.5, 150))) is None  # 8900 m
    assert step_results(steps, stream((3640, 2.5, 150)))[0]["metres"] == 9100


def test_coverage_is_judged_per_kind_of_goal():
    """All the time steps done doesn't make up for the distance steps left out."""
    steps = {"warmup": {"goal": {"time_s": 3600}},
             "blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"distance_m": 1000}}]}]}
    assert step_results(steps, stream((3600, 2.5, 150), (200, 2.5, 150))) is None  # 500 of 1000 m


def test_a_step_barely_started_is_not_reported():
    steps = {"blocks": [{"repeat": 10, "steps": [{"kind": "work", "goal": {"time_s": 300}}]}]}
    assert len(step_results(steps, stream((2880, 3.0, 150)))) == 10  # the tenth is 180 of 300 s
    rows = step_results(steps, stream((2780, 3.0, 150)))  # the tenth is 80 of 300 s
    assert [r["repeat"] for r in rows] == list(range(1, 10))


def test_an_unfinished_step_reports_what_was_done():
    steps = {"blocks": [{"repeat": 10, "steps": [{"kind": "work", "goal": {"time_s": 300}}]}]}
    last = step_results(steps, stream((2880, 3.0, 150)))[-1]
    assert (last["goal"], last["seconds"], last["metres"]) == ({"time_s": 300}, 180, 540)


def test_no_stream_gets_no_results():
    assert step_results(TEMPO, None) is None
    assert step_results(TEMPO, SimpleNamespace(t_offset=[], speed=None, hr=None, distance=None)) is None
    assert step_results(TEMPO, SimpleNamespace(t_offset=[0, 1], speed=[3, 3], hr=[150, 150], distance=None)) is None
    assert step_results(TEMPO, SimpleNamespace(t_offset=[0, 1], speed=None, hr=None, distance=[None, None])) is None


def test_gps_gap_inside_the_steps_gets_no_results():
    """Where the distance jumped ahead the steps can't be placed exactly, and a wrong result is worse than none."""
    s = tempo_stream()
    for i in range(700, 760):
        s.distance[i] = None
    assert step_results(TEMPO, s) is None


def test_samples_missing_inside_the_steps_get_no_results():
    s = tempo_stream()
    del s.t_offset[700:760], s.speed[700:760], s.hr[700:760], s.distance[700:760]
    assert step_results(TEMPO, s) is None


def test_clock_jumping_back_gets_no_results():
    s = tempo_stream()
    s.t_offset = s.t_offset[:700] + [t - 100 for t in s.t_offset[700:]]
    assert step_results(TEMPO, s) is None


def test_short_gaps_and_a_gap_in_the_open_part_are_fine():
    s = tempo_stream()
    for i in range(700, 710):
        s.distance[i] = None
    for i in range(2300, 2400):  # the open cool-down
        s.distance[i] = None
    rows = step_results(TEMPO, s, Z)
    assert (rows[1]["seconds"], rows[1]["metres"]) == (300, 900)


def test_distance_missing_at_the_start_counts_from_zero():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 100}}]}]}
    s = stream((100, 3.0, 150))
    s.distance[:6] = [None] * 6
    row = step_results(steps, s)[0]
    assert (row["seconds"], row["metres"]) == (100, 300)


# ---- facts


def test_planned_ride_has_parts(conn):
    conn.execute(text("update profile set ftp_override = 168"))
    add(conn, day="2026-10-29", sport="bike", title="Sweet Spot 3x10", note="Keep it smooth", zwift=SWEET_SPOT)
    aid = add_session(conn, "bike", START, 3900, source="zwift", avg_power=128, power=[151] * 3900, hr=[140] * 3900)
    f = facts(conn, NOW, aid)
    assert f["plan"]["title"] == "Sweet Spot 3x10" and f["plan"]["note"] == "Keep it smooth"
    assert f["plan"]["optional"] is False and f["plan"]["kind"] == "zwift" and f["rest_day"] is False
    assert [p["label"] for p in f["comparison"]["parts"]] == ["Interval 1", "Interval 2", "Interval 3"]
    assert f["comparison"]["intervals_on_target"] is True
    assert f["workout"]["avg_power"] == 128 and f["workout"]["sport"] == "bike"
    assert f["step_results"] is None and f["matched_by"] is None


def test_planned_run_has_splits_and_zones(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    aid = add_run(conn)
    f = facts(conn, NOW, aid)
    assert f["plan"]["kind"] == "targets" and f["plan"]["steps"]["blocks"][0]["repeat"] == 4
    assert f["plan"]["zone_bpm"]["2"] == [137, 156]
    assert f["comparison"]["splits"][0]["km"] == 1 and sum(f["comparison"]["zones"].values()) > 0
    assert len(f["step_results"]) == 9 and f["step_results"][0]["in_target"] is True
    assert f["matched_by"] == MATCHED_BY == "the plan's order and lengths from the start of the run"


def test_km_splits_of_a_stepped_run_are_not_judged_against_its_work_pace(conn):
    """The band is the work steps'; a km of warm-up isn't "slower" than it."""
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    aid = add_run(conn)
    assert all("status" not in s for s in facts(conn, NOW, aid)["comparison"]["splits"])


def test_km_splits_of_a_run_without_steps_keep_their_status(conn):
    add(conn, day="2026-10-29", sport="run", title="Steady", targets={"duration_s": 3000, "pace_low": 330, "pace_high": 420})
    aid = add_run(conn)
    f = facts(conn, NOW, aid)
    assert f["comparison"]["splits"][0]["status"] == "on_target" and f["step_results"] is None


def test_zone_1_starts_at_60_percent_as_on_the_watch(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}, "target": {"hr_zone": 1}}]}]}
    add(conn, day="2026-10-29", sport="run", title="Very easy", targets={"steps": steps, "hr_zone": 1})
    aid = add_run(conn, stream((600, 2.5, 100)))
    f = facts(conn, NOW, aid)
    assert f["step_results"][0]["in_target"] is False  # 100 bpm is under 114
    assert f["plan"]["zone_bpm"]["1"] == [114, 137] and f["plan"]["hr_bpm"] == [114, 137]
    assert hr_ranges(conn, NOW)[1] == (114, 137)


def test_max_hr_unknown_gives_no_zone_judgement(conn):
    conn.execute(text("update profile set max_hr_override = null, date_of_birth = null"))
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    aid = add_session(conn, "run", START, 2580, distance_m=6000)  # no HR anywhere, so no max HR to find
    s = tempo_stream()
    s.hr = None
    save_stream(conn, aid, s)
    f = facts(conn, NOW, aid)
    assert f["step_results"][0]["in_target"] is None and "zone_bpm" not in f["plan"]
    assert f["step_results"][1]["in_target"] is True  # pace needs no max HR
    assert f["comparison"]["zones"] is None


def test_gym_has_rows(conn):
    add_gym(conn, START - timedelta(days=5), [(BENCH, 80, 8, "normal")] * 3, title="Push")
    add(conn, day="2026-10-29", sport="gym", title="Push", routine="Push")
    aid = add_gym(conn, START, [(BENCH, 80, 9, "normal")] * 3, title="Push")
    f = facts(conn, NOW, aid)
    assert [(r["exercise"], r["status"]) for r in f["comparison"]["rows"]] == [(BENCH, "done")]
    assert f["plan"]["kind"] == "gym" and f["plan"]["items"][0]["exercise"] == BENCH
    json.dumps(f)


def test_unplanned_run_has_no_plan(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    aid = add_run(conn)
    f = facts(conn, NOW, aid)
    assert f["plan"] is None and f["rest_day"] is False and f["step_results"] is None and f["matched_by"] is None
    assert f["comparison"]["splits"][0]["status"] is None and sum(f["comparison"]["zones"].values()) > 0
    assert f["workout"]["sport"] == "run" and f["workout"]["start_at"].startswith("2026-10-29T")
    json.dumps(f)


def test_unplanned_gym_has_its_sets(conn):
    aid = add_gym(conn, START, [(BENCH, 40, 10, "warmup"), (BENCH, 80, 8, "normal")], title="Whatever")
    f = facts(conn, NOW, aid)
    assert f["plan"] is None
    sets = f["comparison"]["sets"]
    assert [(s["exercise"], s["set_type"], s["weight_kg"], s["reps"]) for s in sets] == [
        (BENCH, "warmup", 40, 10), (BENCH, "normal", 80, 8)]
    json.dumps(f)


def test_rest_day_is_flagged(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    add(conn, day="2026-10-29", sport="rest", title="Rest")
    aid = add_run(conn)
    f = facts(conn, NOW, aid)
    assert f["plan"] is None and f["rest_day"] is True
    assert f["comparison"]["splits"] and f["comparison"]["zones"]  # the run's own, not the rest item's


def test_easy_back_follows_the_workout_with_or_without_a_plan(conn):
    timeoff.create(conn, TimeOffIn(reason="injury", label="Knee", start=date(2026, 10, 1), restrictions=[
        Restriction(category="run", until=date(2026, 10, 20))]))
    note = "First two weeks back after your time off: keep it easy."
    aid = add_run(conn)
    assert facts(conn, NOW, aid)["easy_back"] == note
    rest = add(conn, day="2026-10-29", sport="rest", title="Rest")
    assert facts(conn, NOW, aid)["easy_back"] == note
    conn.execute(text("delete from agenda_items where id = :i"), {"i": rest})
    add(conn, day="2026-10-29", sport="run", title="Run", targets={"duration_s": 1800})
    assert facts(conn, NOW, aid)["easy_back"] == note
    ride = add_session(conn, "bike", START + timedelta(hours=1), 3600)
    assert facts(conn, NOW, ride)["easy_back"] is None


def test_no_raw_series(conn):
    conn.execute(text("update profile set ftp_override = 168, max_hr_override = 190"))
    add(conn, day="2026-10-29", sport="bike", title="Ride", zwift=SWEET_SPOT)
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    ride = add_session(conn, "bike", START, 3900, source="zwift", power=[151] * 3900, hr=[140] * 3900)
    run = add_run(conn, start=START + timedelta(hours=2))
    free = add_run(conn, start=START - timedelta(days=1))
    for aid in (ride, run, free):
        f = facts(conn, NOW, aid)
        assert all(len(x) <= 100 for x in lists_in(json.loads(json.dumps(f))))
        for section in (f["workout"], f["comparison"]):
            assert not {"power", "hr", "pace"} & set(section)


def test_recent_is_same_sport_and_earlier(conn):
    def run(days, **fields):
        return add_session(conn, "run", START - timedelta(days=days), 1800, distance_m=5000, avg_hr=150, avg_pace=360, **fields)

    for days in (40, 30, 20, 10):
        run(days)
    add_session(conn, "bike", START - timedelta(days=1), 3600, avg_power=150)
    run(2, sub_type="walking")
    original = run(12)
    run(3, superseded_by=original)
    aid = add_session(conn, "run", START, 1800, distance_m=5000)
    run(-1)  # after this one
    recent = facts(conn, NOW, aid)["recent"]
    assert [r["date"] for r in recent] == ["2026-10-19", "2026-10-17", "2026-10-09"]
    assert recent[0]["distance_m"] == 5000 and recent[0]["avg_hr"] == 150 and recent[0]["avg_pace_s_per_km"] == 360
    assert recent[0]["duration_s"] == 1800 and "id" not in recent[0] and "source" not in recent[0]


def test_goals_are_one_line_each(conn):
    conn.execute(text("insert into goals (text, status) values ('Run 10 km under 50 min', 'active'), ('Old', 'achieved')"))
    aid = add_run(conn)
    assert facts(conn, NOW, aid)["goals"] == ["Run 10 km under 50 min"]


def test_unknown_activity_is_a_lookup_error(conn):
    with pytest.raises(LookupError):
        facts(conn, NOW, 999)
