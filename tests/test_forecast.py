from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin.agenda.store import ItemIn, create
from lockedin.app import app
from lockedin.fitness import record_zwift_ftp
from lockedin.forecast import forecast
from lockedin.forecast.race import riegel
from lockedin.routes.overview import get_now

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
BENCH = "Bench Press (Barbell)"
SWEET_SPOT = {"blocks": [{"type": "intervals", "repeat": 3, "on_s": 600, "off_s": 300, "on_power": 0.9, "off_power": 0.55}]}


def goal(conn, text_, area="gym", exercise=None, created=NOW - timedelta(weeks=12)):
    conn.execute(text("insert into goals (text, area, exercise, created_at) values (:t, :a, :e, :c)"),
                 {"t": text_, "a": area, "e": exercise, "c": created})


def bench_weeks(conn, weeks=12, start_kg=70.0, per_week=1.0):
    for i in range(weeks):
        add_gym(conn, NOW - timedelta(weeks=weeks - 1 - i, hours=2), [(BENCH, start_kg + per_week * i, 5, "normal")])


def only_goal(conn):
    [g] = forecast(conn, NOW)["goals"]
    return g


def test_a_rising_lift_is_on_track_for_its_date(conn):
    bench_weeks(conn)
    goal(conn, "Bench 110 kg by March 2027", exercise=BENCH)
    g = only_goal(conn)
    assert (g["kind"], g["unit"], g["lower_is_better"], g["target"]) == ("lift", "kg", False, 110)
    assert g["deadline"] == "2027-03-31" and g["status"] == "on_track"
    assert len(g["history"]) >= 8 and g["history"][-1][1] == pytest.approx(94.5, abs=0.1)
    assert g["projection"] and g["eta"]["early"] <= g["eta"]["likely"] <= g["eta"]["late"]
    assert g["summary"].startswith("On track for 31 Mar: around ")


def test_without_a_date_it_says_when(conn):
    bench_weeks(conn)
    goal(conn, "Bench 110 kg", exercise=BENCH)
    g = only_goal(conn)
    assert g["status"] == "eta" and g["summary"].startswith("Around ") and "(likely " in g["summary"]


def test_flat_lift_is_not_at_this_pace(conn):
    bench_weeks(conn, per_week=0.0)
    goal(conn, "Bench 110 kg by March 2027", exercise=BENCH)
    g = only_goal(conn)
    assert g["status"] == "not_at_this_pace" and g["eta"] is None
    assert "you'd need +" in g["summary"] and "kg a week" in g["summary"]


def test_two_sessions_are_too_little_data(conn):
    bench_weeks(conn, weeks=2)
    goal(conn, "Bench 110 kg", exercise=BENCH)
    g = only_goal(conn)
    assert g["status"] == "too_little_data" and g["projection"] == [] and g["eta"] is None


def test_reached(conn):
    bench_weeks(conn, start_kg=100)
    goal(conn, "Bench 110 kg", exercise=BENCH)
    assert only_goal(conn)["status"] == "reached"


def test_a_time_goal_comes_down(conn):
    for i in range(10):
        add_session(conn, "run", NOW - timedelta(weeks=9 - i, hours=3), 1680 - 10 * i, distance_m=5000)
    goal(conn, "Run 5k under 25 min", area="run")
    g = only_goal(conn)
    assert (g["kind"], g["unit"], g["lower_is_better"]) == ("time", "min", True)
    assert g["history"][-1][1] == pytest.approx(26.5, abs=0.1) and g["status"] == "eta"


def test_unmeasurable_goals_are_left_out(conn):
    goal(conn, "Feel fitter", area="general")
    assert forecast(conn, NOW)["goals"] == []


def test_riegel():
    assert riegel(3000, 10, 5) == pytest.approx(3000 * 0.5 ** 1.06)


def test_race_times_from_recent_runs(conn):
    add_session(conn, "run", NOW - timedelta(days=10), 3000, distance_m=10000)
    add_session(conn, "run", NOW - timedelta(days=20), 1500, distance_m=4000)  # slower per km: not the source
    race = forecast(conn, NOW)["race"]
    names = [p["name"] for p in race["predictions"]]
    assert names == ["5k", "10k", "Half marathon"]
    five = race["predictions"][0]
    assert five["seconds"] == round(riegel(3000, 10, 5)) and five["from"]["km"] == 10.0
    assert race["history"] and "training runs" in race["note"]


def test_no_runs_no_race(conn):
    assert forecast(conn, NOW)["race"] is None


def test_fitness_ahead_follows_the_plan(conn):
    for d in range(1, 29):
        add_session(conn, "bike", NOW - timedelta(days=d), 3600, source="zwift", np=150)
    conn.execute(text("update activities set tss = 30"))
    create(conn, NOW, ItemIn(day="2026-10-29", sport="bike", title="Sweet Spot", zwift=SWEET_SPOT), "coach")
    days = forecast(conn, NOW)["fitness"]["days"]
    assert days[0]["day"] == "2026-09-30" and days[-1]["day"] == "2026-11-10"
    assert [d["planned"] for d in days].index(True) == 28  # tomorrow on
    planned = {d["day"]: d for d in days}
    assert planned["2026-10-29"]["fatigue"] > planned["2026-10-28"]["fatigue"]


def test_ftp_from_zwift(conn):
    record_zwift_ftp(conn, date(2026, 10, 17), 157)
    record_zwift_ftp(conn, date(2026, 10, 26), 166)
    ftp = forecast(conn, NOW)["ftp"]
    assert (ftp["now"], ftp["source"]) == (166, "zwift")
    assert ftp["history"] == [["2026-10-17", 157], ["2026-10-26", 166]]
    assert ftp["summary"] == "Zwift's FTP: 166 W since 26 Oct, up from 157."


def test_endpoint(client, clean_db):
    app.dependency_overrides[get_now] = lambda: NOW
    r = client.get("/api/forecast", headers=owner_headers())
    assert r.status_code == 200 and set(r.json()) == {"goals", "race", "fitness", "ftp"}
