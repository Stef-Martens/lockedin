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
from lockedin.verdict.facts import facts

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


def lap(seconds, speed, hr, step, intensity):
    return {"start_s": 0, "timer_s": seconds, "elapsed_s": seconds, "distance_m": seconds * speed, "avg_hr": hr,
            "avg_speed": speed, "intensity": intensity, "trigger": "time", "step_index": step}


def set_laps(conn, aid, laps):
    conn.execute(text("update activities set laps = cast(:l as jsonb) where id = :i"), {"l": json.dumps(laps), "i": aid})


def lists_in(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from lists_in(v)
    elif isinstance(value, list):
        yield value
        for v in value:
            yield from lists_in(v)


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
    assert f["blocks"] is None and "step_results" not in f and "matched_by" not in f


def test_planned_run_has_splits_and_zones(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    aid = add_run(conn)
    f = facts(conn, NOW, aid)
    assert f["plan"]["kind"] == "targets" and f["plan"]["steps"]["blocks"][0]["repeat"] == 4
    assert f["plan"]["zone_bpm"]["2"] == [137, 156]
    assert f["comparison"]["splits"][0]["km"] == 1 and sum(f["comparison"]["zones"].values()) > 0
    assert f["blocks"] is None and "step_results" not in f and "matched_by" not in f


def test_blocks_come_from_the_laps(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    aid = add_run(conn)
    set_laps(conn, aid, [lap(600, 2.5, 140, 0, "warmup"), lap(300, 3.0, 160, 1, "active"),
                         lap(120, 2.0, 130, 2, "recovery")])
    f = facts(conn, NOW, aid)
    assert f["blocks"]["follows_plan"] is True and [r["kind"] for r in f["blocks"]["rows"]] == ["warmup", "work", "recovery"]
    assert f["blocks"]["rows"][1]["in_target"] is True and "laps" not in f["workout"]


def test_free_run_has_blocks_without_judgement(conn):
    aid = add_run(conn)
    set_laps(conn, aid, [lap(600, 2.5, 140, 0, "warmup")])
    b = facts(conn, NOW, aid)["blocks"]
    assert b["follows_plan"] is False and b["rows"][0]["in_target"] is None


def test_zone_1_starts_at_60_percent_as_on_the_watch(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}, "target": {"hr_zone": 1}}]}]}
    add(conn, day="2026-10-29", sport="run", title="Very easy", targets={"steps": steps, "hr_zone": 1})
    aid = add_run(conn, stream((600, 2.5, 100)))
    set_laps(conn, aid, [lap(600, 2.5, 100, 0, "active")])
    f = facts(conn, NOW, aid)
    assert f["blocks"]["rows"][0]["in_target"] is False  # 100 bpm is under 114
    assert f["plan"]["zone_bpm"]["1"] == [114, 137] and f["plan"]["hr_bpm"] == [114, 137]
    assert hr_ranges(conn, NOW)[1] == (114, 137)


def test_max_hr_unknown_gives_no_zone_judgement(conn):
    conn.execute(text("update profile set max_hr_override = null, date_of_birth = null"))
    add(conn, day="2026-10-29", sport="run", title="Tempo", targets={"steps": TEMPO})
    aid = add_session(conn, "run", START, 2580, distance_m=6000)  # no HR anywhere, so no max HR to find
    s = tempo_stream()
    s.hr = None
    save_stream(conn, aid, s)
    set_laps(conn, aid, [lap(600, 2.5, 140, 0, "warmup"), lap(300, 3.0, 160, 1, "active")])
    f = facts(conn, NOW, aid)
    assert f["blocks"]["rows"][0]["in_target"] is None and "zone_bpm" not in f["plan"]
    assert f["blocks"]["rows"][1]["in_target"] is True  # 3.0 m/s is 5:33 in 5:30-5:50; pace needs no max HR
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
    assert f["plan"] is None and f["rest_day"] is False and f["blocks"] is None
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
