from datetime import UTC, date, datetime, timedelta

import pytest
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin import timeoff
from lockedin.agenda.store import ItemIn, create
from lockedin.forecast import forecast
from lockedin.forecast.goals import goal_category
from lockedin.forecast.trend import fit, project
from lockedin.timeoff import Restriction, TimeOffIn

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
TODAY = date(2026, 10, 27)
BENCH = "Bench Press (Barbell)"


def goal(conn, text_, area="gym", exercise=None):
    conn.execute(text("insert into goals (text, area, exercise, created_at) values (:t, :a, :e, :c)"),
                 {"t": text_, "a": area, "e": exercise, "c": NOW - timedelta(weeks=20)})


def off(conn, start, reason="injury", label="Knee operation", **until):
    return timeoff.create(conn, TimeOffIn(reason=reason, label=label, start=start, restrictions=[
        Restriction(category=c, until=u) for c, u in until.items()]))


def only_goal(conn):
    [g] = forecast(conn, NOW)["goals"]
    return g


def step(g):  # the projection's gain in its second week: today's slope, as the chart shows it
    return g["projection"][1][1] - g["projection"][0][1]


def days(start, n):
    return {start + timedelta(days=i) for i in range(n)}


def test_fit_runs_on_training_days():
    straight = [(TODAY - timedelta(weeks=k), 100.0 - k) for k in range(12)]
    gap = days(TODAY - timedelta(weeks=10) + timedelta(days=1), 28)  # four of the five weeks between two sessions
    with_gap = [(d - timedelta(weeks=4) if k >= 6 else d, v) for k, (d, v) in enumerate(straight)]
    t = fit(with_gap, TODAY, off_days=gap)
    assert t.per_week == pytest.approx(1.0) and t.at_today == pytest.approx(100.0)
    assert fit(with_gap, TODAY).per_week < 0.8  # read on the calendar, the month off looks like a slowdown


def test_min_span_counts_training_days():
    pts = [(TODAY - timedelta(days=d), 80.0) for d in (0, 7, 14, 35)]
    assert fit(pts, TODAY) is not None
    assert fit(pts, TODAY, off_days=days(TODAY - timedelta(days=34), 14)) is None  # 21 training days


def test_projection_pauses_through_time_off_and_settling_in():
    t = fit([(TODAY - timedelta(weeks=k), 100.0 - k + (0.3 if k % 2 else -0.3)) for k in range(12)], TODAY)
    window = days(TODAY + timedelta(days=8), 14)  # 4–17 Nov off, then settling in until 1 Dec
    plain, paused = project(t, 10, flatten=False), project(t, 10, flatten=False, off_days=window)
    assert [p[0] for p in paused] == [p[0] for p in plain]
    week = t.at_today + 7 * t.per_day
    assert [p[1] for p in paused[:5]] == pytest.approx([week] * 5)  # 3 Nov, then no gain until 1 Dec
    assert paused[5][1] == pytest.approx(t.at_today + 14 * t.per_day)  # 8 Dec: a week on from 1 Dec
    assert paused[-1][1] == pytest.approx(plain[-1][1] - 28 * t.per_day)
    assert paused[4][3] - paused[4][2] == pytest.approx(paused[0][3] - paused[0][2])  # the band waits too
    assert paused[4][3] - paused[4][2] < plain[4][3] - plain[4][2]


def test_a_past_upper_month_keeps_the_bench_slope(conn):
    goal(conn, "Bench 110 kg", exercise=BENCH)
    for i in range(12):  # twelve training weeks in a row
        add_gym(conn, NOW - timedelta(weeks=11 - i, hours=2), [(BENCH, 70.0 + i, 5, "normal")])
    steady = only_goal(conn)
    conn.execute(text("delete from activities"))

    for i in range(12):  # the same twelve weeks with four weeks off after the sixth
        add_gym(conn, NOW - timedelta(weeks=(15 - i) if i < 6 else (11 - i), hours=2), [(BENCH, 70.0 + i, 5, "normal")])
    calendar = only_goal(conn)
    off(conn, (NOW - timedelta(weeks=10)).date() + timedelta(days=4), upper=(NOW - timedelta(weeks=6)).date() + timedelta(days=3))
    g = only_goal(conn)
    assert step(g) == pytest.approx(step(steady), rel=0.1)
    assert step(calendar) < 0.9 * step(steady)  # on the calendar, the month off reads as a slowdown

    add_gym(conn, NOW - timedelta(weeks=8, hours=2), [(BENCH, 40.0, 5, "normal")])  # one light try while it was off
    tried = only_goal(conn)
    assert (NOW - timedelta(weeks=8)).date().isoformat() not in [d for d, _ in tried["history"]]
    assert tried["history"] == g["history"] and len(g["history"]) == 12


def test_future_upper_time_off_pushes_the_eta_back(conn):
    for i in range(12):
        add_gym(conn, NOW - timedelta(weeks=11 - i, hours=2), [(BENCH, 70.0 + i, 5, "normal")])
    goal(conn, "Bench 110 kg", exercise=BENCH)
    before = date.fromisoformat(only_goal(conn)["eta"]["likely"])
    off(conn, date(2026, 11, 10), upper=date(2026, 12, 7))  # 28 days, then 14 settling in
    g = only_goal(conn)
    assert date.fromisoformat(g["eta"]["likely"]) >= before + timedelta(days=28 + 14)
    likely = {d: m for d, m, _, _ in g["projection"]}
    assert {likely[d] for d in ("2026-11-10", "2026-11-17", "2026-12-01", "2026-12-15")} == {likely["2026-11-10"]}
    assert likely["2026-12-22"] > likely["2026-12-15"]


def test_a_run_goal_ignores_upper_body_time_off(conn):
    for i in range(10):
        add_session(conn, "run", NOW - timedelta(weeks=9 - i, hours=3), 1680 - 10 * i, distance_m=5000)
    goal(conn, "Run 5k under 25 min", area="run")
    before = only_goal(conn)
    off(conn, (NOW - timedelta(weeks=6)).date(), upper=(NOW + timedelta(weeks=8)).date())
    assert only_goal(conn) == before
    off(conn, (NOW + timedelta(weeks=2)).date(), run=(NOW + timedelta(weeks=4)).date())
    assert only_goal(conn)["eta"] != before["eta"]


def test_goal_category(conn):
    def cat(kind, **g):
        return goal_category(conn, NOW, {"id": 1, "text": "", **g}, kind)
    assert cat("lift", area="gym", exercise=BENCH) == "upper"
    assert cat("lift", area="gym", exercise="Leg Press Horizontal (Machine)") == "lower"
    assert cat("lift", area="gym", exercise="Cable Crunch") == "core"
    assert cat("lift", area="gym", exercise="Made-up lift") is None
    assert cat("ftp", area="bike") == "bike"
    assert (cat("time", area="run"), cat("distance", area="swim")) == ("run", "swim")
    assert cat("body", area="body") is None


def test_fitness_ahead_adds_no_load_for_a_clashing_session(conn):
    for d in range(1, 29):
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift", np=150)
    conn.execute(text("update activities set tss = 30"))

    def by_day():
        return {d["day"]: d for d in forecast(conn, NOW)["fitness"]["days"]}
    nothing = by_day()
    create(conn, NOW, ItemIn(day="2026-10-29", sport="run", title="Tempo run", targets={"duration_s": 3600}), "manual")
    planned = by_day()
    assert planned["2026-10-29"]["fatigue"] > nothing["2026-10-29"]["fatigue"]
    off(conn, date(2026, 10, 28), run=date(2026, 11, 5))
    assert by_day() == nothing


def test_forecast_lists_time_off_for_the_charts(conn):
    off(conn, date(2026, 12, 3), run=date(2026, 12, 17), upper=date(2027, 1, 2))
    off(conn, date(2026, 3, 1), reason="vacation", label="Long ago", all=date(2026, 3, 8))  # over 26 weeks ago
    assert forecast(conn, NOW)["time_off"] == [
        {"start": "2026-12-03", "end": "2027-01-02", "reason": "injury", "label": "Knee operation"}]
