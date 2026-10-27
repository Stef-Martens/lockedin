"""The owner's own case end to end: an operation on 3 Dec, everything off until 5 Dec, no running until 17 Dec,
no upper body until 2 Jan."""

from datetime import UTC, date, datetime, timedelta

from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin import timeoff
from lockedin.app import app
from lockedin.coach.prompt import turn_context
from lockedin.focus.mix import session_suggestions
from lockedin.focus.suggest import gym_suggestions
from lockedin.plan.build import build_plan
from lockedin.routes.overview import get_now
from lockedin.timeoff import REGIONS, Restriction, TimeOffIn

H = owner_headers()
BENCH, RAISE = "Bench Press (Barbell)", "Lateral Raise (Dumbbell)"
UPPER = "Upper"


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)


def upper_day(conn, day: date, bench_kg: float):
    add_gym(conn, at(day), [(BENCH, bench_kg, 8, "normal")] * 3 + [(RAISE, 10, 12, "normal")] * 3, title=UPPER)


def owner_case(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    for weeks in range(8, 0, -1):  # mostly gym, two upper days a week, before the operation
        upper_day(conn, date(2026, 12, 2) - timedelta(weeks=weeks), 60)
        upper_day(conn, date(2026, 12, 2) - timedelta(weeks=weeks, days=3), 60)
    upper_day(conn, date(2026, 12, 1), 60)
    for d in (28, 30):  # steady runs: on a normal day this asks for intervals
        add_session(conn, "run", at(date(2026, 11, d)), 2700, avg_hr=160, distance_m=7000)
    add_session(conn, "run", at(date(2026, 12, 2)), 2700, avg_hr=160, distance_m=7000)
    timeoff.create(conn, TimeOffIn(reason="injury", label="Operation", start=date(2026, 12, 3), restrictions=[
        Restriction(category="all", until=date(2026, 12, 5)), Restriction(category="run", until=date(2026, 12, 17)),
        Restriction(category="upper", until=date(2027, 1, 2))]))


def test_coach_context_lists_all_three_restrictions(conn):
    owner_case(conn)
    ctx = turn_context(conn, at(date(2026, 12, 1)))
    assert ("Time off: Operation from 3 Dec: no running until 17 Dec, no upper body until 2 Jan, "
            "everything off until 5 Dec") in ctx


def test_overview_on_10_dec_suggests_nothing_restricted(client, clean_db):
    with clean_db.begin() as c:
        owner_case(c)
    app.dependency_overrides[get_now] = lambda: at(date(2026, 12, 10))
    data = client.get("/api/overview", headers=H).json()
    assert data["time_off_today"] == "no running until 17 Dec, no upper body until 2 Jan"
    assert data["comeback"]["suggestion"] == "Ease back in with something easy your time off allows."
    assert "full-body" not in str(data)


def test_planner_eases_only_the_first_upper_session_back(conn):
    owner_case(conn)
    for d in (date(2026, 12, 20), date(2026, 12, 27), date(2027, 1, 1)):  # running again, so not a comeback
        add_session(conn, "run", at(d), 2400, avg_hr=140, distance_m=6000)

    def bench(day: date) -> dict:
        return next(i for i in build_plan(conn, at(day), UPPER)["items"] if i["exercise"] == BENCH)
    first = bench(date(2027, 1, 3))
    assert first["change"] == "eased" and first["weight_kg"] < 60 and not first["skipped"]
    upper_day(conn, date(2027, 1, 3), first["weight_kg"])
    second = bench(date(2027, 1, 6))
    assert second["change"] != "eased" and second["weight_kg"] == first["weight_kg"]
    upper_day(conn, date(2027, 1, 6), second["weight_kg"])
    third = bench(date(2027, 1, 9))
    assert third["change"] != "eased" and third["weight_kg"] == first["weight_kg"]


def test_focus_tips_on_18_dec_have_no_hard_run(conn):
    owner_case(conn)
    now = at(date(2026, 12, 18))
    tips = session_suggestions(conn, now)
    assert tips and all(s.sport == "run" for s in tips)
    assert not any(s.kind == "hard" for s in tips)
    upper = conn.execute(text("select key from muscles where region = any(:r)"), {"r": list(REGIONS["upper"])}).scalars()
    assert not {g.muscle_key for g in gym_suggestions(conn, now, limit=20)} & set(upper)
