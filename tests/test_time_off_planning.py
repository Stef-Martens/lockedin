from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import owner_headers
from focus_helpers import add_gym, add_session
from sqlalchemy import text

from lockedin import timeoff
from lockedin.agenda.store import ItemIn, create
from lockedin.app import app
from lockedin.focus.mix import session_suggestions
from lockedin.focus.musclemap import muscle_map
from lockedin.focus.suggest import gym_suggestions
from lockedin.plan.build import build_plan
from lockedin.routes.overview import get_now
from lockedin.timeoff import Restriction, TimeOffIn

H = owner_headers()
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
TODAY = date(2026, 10, 26)
BENCH, SQUAT = "Bench Press (Barbell)", "Squat (Barbell)"
MIXED, UPPER = "Mixed", "Upper"


def off(conn, start=TODAY, **until):
    timeoff.create(conn, TimeOffIn(reason="injury", start=start, restrictions=[
        Restriction(category=c, until=u) for c, u in until.items()]))


def items_by(plan: dict) -> dict:
    return {i["exercise"]: i for i in plan["items"]}


def mixed_day(conn, when=NOW - timedelta(days=3), title=MIXED):
    add_gym(conn, when, [(BENCH, 60, 8, "normal")] * 3 + [(SQUAT, 80, 8, "normal")] * 3, title=title)


def test_planner_skips_restricted_exercises(conn):
    mixed_day(conn)
    off(conn, upper=date(2027, 1, 2))
    items = items_by(build_plan(conn, NOW, MIXED))
    assert items[BENCH]["skipped"] is True and items[BENCH]["reason"] == "Upper body is off until 2 Jan"
    assert items[SQUAT]["skipped"] is False and items[SQUAT]["reason"] is None


def test_planner_says_when_nothing_is_left(conn):
    add_gym(conn, NOW - timedelta(days=3), [(BENCH, 60, 8, "normal")] * 3
            + [("Lateral Raise (Dumbbell)", 12, 12, "normal")] * 3, title=UPPER)
    off(conn, upper=date(2027, 1, 2))
    plan = build_plan(conn, NOW, UPPER)
    assert all(i["skipped"] for i in plan["items"]) and len(plan["items"]) == 2
    assert plan["note"] == "Upper body is off until 2 Jan; nothing left of this routine."
    assert not any(i["kind"] != "routine" for i in plan["items"])


def test_first_days_back_are_eased(conn):
    mixed_day(conn, NOW - timedelta(days=10))
    add_session(conn, "run", NOW - timedelta(days=1), 2700)  # not a comeback: they kept running
    off(conn, start=TODAY - timedelta(days=20), upper=TODAY - timedelta(days=1))
    items = items_by(build_plan(conn, NOW, MIXED))
    assert (items[BENCH]["change"], items[BENCH]["weight_kg"]) == ("eased", 52.5)  # 54 rounded down to 2.5
    assert items[BENCH]["reason"] == "Back after your time off: lighter to ease in" and items[BENCH]["skipped"] is False
    assert items[SQUAT]["change"] != "eased"
    later = items_by(build_plan(conn, NOW + timedelta(days=14), MIXED))  # 15 days after: back to normal
    assert later[BENCH]["change"] != "eased"


def test_easing_does_not_compound_after_the_first_session_back(conn):
    mixed_day(conn, NOW - timedelta(days=10))
    add_session(conn, "run", NOW - timedelta(days=1), 2700)
    off(conn, start=TODAY - timedelta(days=20), upper=TODAY - timedelta(days=1))
    add_gym(conn, NOW, [(BENCH, 52.5, 8, "normal")] * 3 + [(SQUAT, 80, 8, "normal")] * 3, title=MIXED)
    bench = items_by(build_plan(conn, NOW + timedelta(days=3), MIXED))[BENCH]
    assert bench["change"] != "eased" and bench["weight_kg"] == 52.5


def test_not_eased_when_the_region_is_off_again(conn):
    mixed_day(conn, NOW - timedelta(days=10))
    add_session(conn, "run", NOW - timedelta(days=1), 2700)
    off(conn, start=TODAY - timedelta(days=20), upper=TODAY - timedelta(days=1))
    off(conn, upper=date(2027, 1, 2))
    bench = items_by(build_plan(conn, NOW, MIXED))[BENCH]
    assert bench["change"] != "eased" and bench["skipped"] is True


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def test_saved_plan_rebuilds_when_time_off_changes(client, clean_db, clock):
    with clean_db.begin() as c:
        mixed_day(c)
    first = client.get("/api/plan", params={"day": MIXED}, headers=H).json()
    assert client.get("/api/plan", params={"day": MIXED}, headers=H).json()["id"] == first["id"]
    assert not any(i["skipped"] for i in first["items"]) and first["note"] is None
    with clean_db.begin() as c:
        off(c, upper=date(2027, 1, 2))
    again = client.get("/api/plan", params={"day": MIXED}, headers=H).json()
    assert again["id"] != first["id"] and items_by(again)[BENCH]["skipped"] is True


def test_plan_note_reaches_the_api(client, clean_db, clock):
    with clean_db.begin() as c:
        add_gym(c, NOW - timedelta(days=3), [(BENCH, 60, 8, "normal")] * 3, title=UPPER)
        off(c, upper=date(2027, 1, 2))
    plan = client.get("/api/plan", params={"day": UPPER}, headers=H).json()
    assert plan["note"] == "Upper body is off until 2 Jan; nothing left of this routine."


def test_focus_tips_skip_restricted_and_away(conn):
    for d in (2, 6, 11, 16):
        add_session(conn, "run", NOW - timedelta(days=d), 2700, avg_hr=160, distance_m=7000)
    add_gym(conn, NOW - timedelta(days=2), [(SQUAT, 80, 8, "normal")] * 3)
    assert {s.sport for s in session_suggestions(conn, NOW)} == {"run"}
    assert any(g.muscle_key == "mid_lower_chest" for g in gym_suggestions(conn, NOW, limit=20))
    off(conn, run=date(2026, 11, 5), upper=date(2026, 11, 5))
    assert session_suggestions(conn, NOW) == []
    assert not any(g.muscle_key == "mid_lower_chest" for g in gym_suggestions(conn, NOW, limit=20))
    assert gym_suggestions(conn, NOW)
    timeoff.create(conn, TimeOffIn(reason="vacation", start=TODAY,
                                   restrictions=[Restriction(category="all", until=date(2026, 10, 30))]))
    assert session_suggestions(conn, NOW) == [] and gym_suggestions(conn, NOW) == []


def test_muscle_map_says_off_until(conn):
    add_gym(conn, NOW - timedelta(days=2), [(SQUAT, 80, 8, "normal")] * 3)
    before = {m["key"]: m for m in muscle_map(conn, NOW, None)["muscles"]}
    assert before["mid_lower_chest"]["suggestion"] and before["mid_lower_chest"]["off_until"] is None
    off(conn, upper=date(2027, 1, 2))
    after = {m["key"]: m for m in muscle_map(conn, NOW, None)["muscles"]}
    assert after["mid_lower_chest"]["off_until"] == "2027-01-02" and after["mid_lower_chest"]["suggestion"] is None
    assert after["quads"]["off_until"] is None
    assert not any(g.muscle_key == "mid_lower_chest" for g in gym_suggestions(conn, NOW, limit=20))


def test_off_muscles_leave_the_muscle_counts(conn):
    add_gym(conn, NOW - timedelta(hours=1), [(BENCH, 60, 8, "normal")] * 3)
    before = muscle_map(conn, NOW, None)
    off(conn, upper=date(2027, 1, 2))
    after = muscle_map(conn, NOW, None)
    upper = [m for m in after["muscles"] if m["off_until"]]
    trained_upper = [m for m in upper if m["sets"] > 0]
    assert upper and trained_upper and any(m["sets"] == 0 for m in upper)
    assert after["total"] == before["total"] - len(upper)
    assert after["trained_count"] == before["trained_count"] - len(trained_upper)


def test_session_page_plans_a_future_gym_day_with_that_days_time_off(client, clean_db, clock):
    with clean_db.begin() as c:
        add_gym(c, NOW - timedelta(days=3), [(BENCH, 60, 8, "normal")] * 3 + [(SQUAT, 80, 8, "normal")] * 3, title=MIXED)
        off(c, start=date(2026, 10, 28), upper=date(2026, 10, 31))
        inside = create(c, NOW, ItemIn(day=date(2026, 10, 29), sport="gym", title="Gym", routine=MIXED), "manual")["id"]
        after = create(c, NOW, ItemIn(day=date(2026, 11, 2), sport="gym", title="Gym", routine=MIXED), "manual")["id"]

    def bench(item_id):
        plan = client.get(f"/api/agenda/{item_id}/detail", headers=H).json()["plan"]
        return items_by(plan)[BENCH]
    assert bench(inside)["skipped"] is True and bench(inside)["off_until"] == "2026-10-31"
    app.dependency_overrides[get_now] = lambda: NOW + timedelta(days=4)  # 30 Oct: upper body is off today
    assert bench(after)["skipped"] is False and bench(after)["off_until"] is None


def test_focus_tips_keep_the_first_two_weeks_back_easy(conn):
    conn.execute(text("update profile set max_hr_override = 190"))
    for d in (2, 6, 11, 16):
        add_session(conn, "run", NOW - timedelta(days=d), 2700, avg_hr=160, distance_m=7000)
    assert any(s.kind == "hard" for s in session_suggestions(conn, NOW))
    off(conn, start=TODAY - timedelta(days=20), run=TODAY - timedelta(days=1))
    assert [s.kind for s in session_suggestions(conn, NOW)] == ["long"]
    conn.execute(text("delete from time_off"))
    off(conn, start=TODAY - timedelta(days=20), run=TODAY - timedelta(days=15))  # back 15 days ago
    assert any(s.kind == "hard" for s in session_suggestions(conn, NOW))


def test_a_goal_brings_an_easy_session_in_the_first_two_weeks_back(conn):
    conn.execute(text("insert into goals (text, area, status) values ('FTP 250 W', 'bike', 'active')"))
    assert session_suggestions(conn, NOW)[0].title == "Intervals"
    off(conn, start=TODAY - timedelta(days=20), bike=TODAY - timedelta(days=1))
    ride = session_suggestions(conn, NOW)[0]
    assert (ride.sport, ride.kind) == ("bike", "easy")
    assert ride.reason == "First two weeks back: keep it easy · toward: FTP 250 W"
