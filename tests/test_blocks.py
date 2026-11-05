from lockedin.agenda.blocks import blocks

STEPS = {"warmup": {"goal": {"time_s": 600}},
         "blocks": [{"repeat": 3, "steps": [
             {"kind": "work", "goal": {"time_s": 480}, "target": {"pace_low": 345, "pace_high": 360}},
             {"kind": "recovery", "goal": {"time_s": 120}}]}],
         "cooldown": {"goal": {"time_s": 600}}}
ZONES = {1: (114, 137), 2: (137, 156), 3: (156, 165)}


def lap(seconds, pace, hr, step, intensity, distance=None):
    speed = 1000 / pace if pace else None
    return {"start_s": 0, "timer_s": seconds, "elapsed_s": seconds, "distance_m": distance or (seconds * speed if speed else None),
            "avg_hr": hr, "avg_speed": speed, "intensity": intensity, "trigger": "time", "step_index": step}


def real_laps():
    return [lap(600, 440, 135, 0, "warmup"), lap(480, 331, 164, 1, "active"), lap(120, 420, 150, 2, "recovery"),
            lap(480, 351, 163, 1, "active"), lap(120, 420, 150, 2, "recovery"), lap(480, 356, 163, 1, "active"),
            lap(120, 420, 150, 2, "recovery"), lap(600, 440, 140, 4, "cooldown")]


def test_blocks_follow_the_plan():
    b = blocks(real_laps(), STEPS, ZONES)
    assert b["follows_plan"] is True and len(b["rows"]) == 8
    work = [r for r in b["rows"] if r["kind"] == "work"]
    assert [(r["seconds"], r["pace_s_per_km"], r["avg_hr"], r["in_target"]) for r in work] == [
        (480, 331, 164, False), (480, 351, 163, True), (480, 356, 163, True)]
    assert work[0]["planned_goal"] == {"time_s": 480} and work[0]["planned_target"]["pace_low"] == 345
    assert [r["repeat"] for r in b["rows"]] == [None, 1, 1, 2, 2, 3, 3, None]
    assert b["rows"][2]["in_target"] is None  # a recovery with no target isn't judged


def test_zone_target_is_judged_on_bpm():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}, "target": {"hr_zone": 2}}]}]}
    assert blocks([lap(600, 400, 150, 0, "active")], steps, ZONES)["rows"][0]["in_target"] is True
    assert blocks([lap(600, 400, 160, 0, "active")], steps, ZONES)["rows"][0]["in_target"] is False
    assert blocks([lap(600, 400, 150, 0, "active")], steps, {})["rows"][0]["in_target"] is None
    assert blocks([lap(600, 400, None, 0, "active")], steps, ZONES)["rows"][0]["in_target"] is None


def test_free_run_has_no_blocks():
    assert blocks([], STEPS, ZONES) is None and blocks(None, STEPS, ZONES) is None
    assert blocks([lap(600, 400, 150, None, "active")], STEPS, ZONES) is None


def test_other_workout_is_not_judged():
    laps = [lap(600, 440, 135, 0, "warmup"), lap(480, 331, 164, 1, "recovery")]
    b = blocks(laps, STEPS, ZONES)
    assert b["follows_plan"] is False and len(b["rows"]) == 2
    assert all(r[k] is None for r in b["rows"] for k in ("planned_goal", "planned_target", "in_target", "repeat"))
    assert b["rows"][1]["pace_s_per_km"] == 331


def test_more_laps_than_steps_does_not_follow():
    steps = {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 600}}]}]}
    assert blocks([lap(600, 400, 150, 0, "active"), lap(60, 400, 150, 1, "active")], steps, ZONES)["follows_plan"] is False


def test_step_cut_short_shows_what_happened():
    laps = real_laps()[:4]
    laps[3] = lap(300, 351, 163, 1, "active")
    b = blocks(laps, STEPS, ZONES)
    assert b["follows_plan"] is True and b["rows"][3]["seconds"] == 300 and b["rows"][3]["planned_goal"] == {"time_s": 480}


def test_run_stopped_early_still_follows():
    b = blocks(real_laps()[:5], STEPS, ZONES)
    assert b["follows_plan"] is True and len(b["rows"]) == 5


def test_no_steps_in_plan_still_shows_blocks_unjudged():
    b = blocks(real_laps(), None, ZONES)
    assert b["follows_plan"] is False and len(b["rows"]) == 8 and b["rows"][1]["pace_s_per_km"] == 331
    assert blocks(real_laps(), {"blocks": []}, ZONES)["follows_plan"] is False


def test_kinds_and_pace_fallbacks():
    laps = [{"timer_s": 300, "distance_m": 1000, "avg_speed": None, "intensity": "interval", "step_index": 0, "avg_hr": None},
            {"timer_s": 60, "distance_m": None, "avg_speed": None, "intensity": "rest", "step_index": 1},
            {"elapsed_s": 90, "intensity": "other", "step_index": 2}]
    rows = blocks(laps, None, {})["rows"]
    assert [r["kind"] for r in rows] == ["work", "recovery", "work"]
    assert rows[0]["pace_s_per_km"] == 300 and rows[1]["pace_s_per_km"] is None and rows[2]["seconds"] == 90
