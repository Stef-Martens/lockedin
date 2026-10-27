"""Run steps: validation, the summary derived from them, and the one-line summary. No database."""

import pytest
from pydantic import ValidationError

from lockedin.agenda.steps import expand, summary_line
from lockedin.agenda.store import ItemIn, Targets

TEMPO = {"warmup": {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
         "blocks": [{"repeat": 4, "steps": [
             {"kind": "work", "goal": {"time_s": 300}, "target": {"pace_low": 330, "pace_high": 350}},
             {"kind": "recovery", "goal": {"time_s": 120}}]}],
         "cooldown": {"goal": {"open": True}}}


def test_summary_line_of_steps():
    assert summary_line("run", {"steps": TEMPO}) == "10' warm-up Z2 · 4 × (5' @ 5:30–5:50, 2' jog) · cool-down"


def test_summary_line_without_steps():
    assert summary_line("run", {"distance_m": 8000, "pace_low": 330, "pace_high": 350, "hr_zone": 2}) == "8 km @ 5:30–5:50 Z2"
    assert summary_line("run", {"duration_s": 2700, "hr_zone": 2}) == "45' Z2"
    assert summary_line("swim", {"distance_m": 1500, "pace_low": 120, "pace_high": 120}) == "1500 m @ 2:00/100 m"
    assert summary_line("swim", {"distance_m": 1500, "pace_low": 115, "pace_high": 125}) == "1500 m @ 1:55–2:05/100 m"
    assert summary_line("run", None) is None and summary_line("run", {}) is None


def test_time_and_distance_words():
    def one(goal):
        return {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": goal}]}]}

    assert summary_line("run", {"steps": one({"time_s": 90})}) == "1'30\""
    assert summary_line("run", {"steps": one({"time_s": 45})}) == "45\""
    assert summary_line("run", {"steps": one({"distance_m": 400})}) == "400 m"
    assert summary_line("run", {"steps": one({"distance_m": 1500})}) == "1.5 km"
    assert summary_line("run", {"steps": one({"distance_m": 1000})}) == "1 km"


def test_derive_tempo():
    t = Targets(steps=TEMPO, distance_m=5000, pace_low=200, pace_high=200)  # sent summary is ignored
    assert (t.duration_s, t.distance_m, t.pace_low, t.pace_high, t.hr_zone) == (None, None, 330, 350, None)


def test_derive_all_time_and_shared_zone():
    steps = {"blocks": [{"repeat": 3, "steps": [{"kind": "work", "goal": {"time_s": 600}, "target": {"hr_zone": 4}},
                                                {"kind": "recovery", "goal": {"time_s": 120}}]}]}
    t = Targets(steps=steps)
    assert (t.duration_s, t.hr_zone, t.pace_low) == (2160, 4, None)


def test_derive_leaves_out_of_range_totals_none():
    steps = {"blocks": [{"repeat": 20, "steps": [{"kind": "work", "goal": {"distance_m": 10_000}}]}]}
    assert Targets(steps=steps).distance_m is None


def test_expand_unrolls_repeats():
    kinds = [s["kind"] for s in expand(TEMPO)]
    assert kinds == ["warmup"] + ["work", "recovery"] * 4 + ["cooldown"]
    assert expand(TEMPO)[1]["repeated"] and not expand(TEMPO)[0]["repeated"]


@pytest.mark.parametrize("bad", [
    {"blocks": []},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60, "distance_m": 400}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 330}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 360, "pace_high": 330}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 330, "pace_high": 350, "hr_zone": 3}}]}]},
    {"blocks": [{"repeat": 21, "steps": [{"kind": "work", "goal": {"time_s": 60}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 100, "pace_high": 120}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"open": False}}]}]},
])
def test_bad_steps_are_refused(bad):
    with pytest.raises(ValidationError):
        Targets(steps=bad)


def test_steps_only_on_runs():
    with pytest.raises(ValidationError, match="Steps are for runs only"):
        ItemIn(day="2026-10-28", sport="swim", title="Swim", targets={"steps": TEMPO})


def test_a_run_with_steps_is_accepted():
    item = ItemIn(day="2026-10-28", sport="run", title="Tempo", targets={"steps": TEMPO})
    assert item.targets.pace_low == 330
