from datetime import UTC, date, datetime

import pytest
from conftest import owner_headers
from sqlalchemy import text

from lockedin import timeoff
from lockedin.app import app
from lockedin.routes.overview import get_now
from lockedin.timeoff import CATEGORIES, Restriction, TimeOffIn

H = owner_headers()
NOW = datetime(2026, 12, 1, 9, tzinfo=UTC)


@pytest.fixture
def clock():
    app.dependency_overrides[get_now] = lambda: NOW


def injury(start=date(2026, 12, 3), **until):
    until = until or {"run": date(2026, 12, 17), "upper": date(2027, 1, 2)}
    return TimeOffIn(reason="injury", start=start, restrictions=[Restriction(category=c, until=u) for c, u in until.items()])


def test_off_on_expands_all_and_is_inclusive(conn):
    timeoff.create(conn, injury())
    assert timeoff.off_on(conn, date(2026, 12, 17)) == {"run": date(2026, 12, 17), "upper": date(2027, 1, 2)}
    assert timeoff.off_on(conn, date(2026, 12, 18)) == {"upper": date(2027, 1, 2)}
    assert timeoff.off_on(conn, date(2026, 12, 2)) == {}


def test_vacation_all_means_away(conn):
    timeoff.create(conn, TimeOffIn(reason="vacation", start=date(2026, 12, 20),
                                   restrictions=[Restriction(category="all", until=date(2026, 12, 27))]))
    assert timeoff.away_on(conn, date(2026, 12, 27)) is True
    assert timeoff.away_on(conn, date(2026, 12, 28)) is False
    assert set(timeoff.off_on(conn, date(2026, 12, 24))) == set(CATEGORIES)


def test_overlap_takes_the_union_and_latest_until(conn):
    timeoff.create(conn, injury())
    timeoff.create(conn, injury(start=date(2026, 12, 10), run=date(2026, 12, 24)))
    timeoff.create(conn, TimeOffIn(reason="vacation", start=date(2026, 12, 20),
                                   restrictions=[Restriction(category="all", until=date(2026, 12, 27))]))
    assert timeoff.off_on(conn, date(2026, 12, 12))["run"] == date(2026, 12, 24)
    off = timeoff.off_on(conn, date(2026, 12, 20))
    assert off["run"] == date(2026, 12, 27)
    assert off["upper"] == date(2027, 1, 2)


def test_off_muscles_by_region(conn):
    timeoff.create(conn, injury(upper=date(2026, 12, 20)))
    off = timeoff.off_muscles(conn, date(2026, 12, 5))
    regions = {"arms", "back", "chest", "shoulders"}
    expected = set(conn.execute(text("select key from muscles where region = any(:r)"), {"r": list(regions)}).scalars())
    assert expected and set(off) == expected and "quads" not in off
    assert set(off.values()) == {date(2026, 12, 20)}
    assert timeoff.off_muscles(conn, date(2026, 12, 21)) == {}


def test_describe(conn):
    timeoff.create(conn, injury())
    assert timeoff.describe(timeoff.off_on(conn, date(2026, 12, 10))) == "no running until 17 Dec, no upper body until 2 Jan"
    assert timeoff.describe({c: date(2026, 12, 27) for c in CATEGORIES}) == "everything off until 27 Dec"
    assert timeoff.describe({}) == ""


def test_entries_entry_on_and_back_from(conn):
    a = timeoff.create(conn, injury())
    b = timeoff.create(conn, injury(start=date(2026, 12, 10), run=date(2026, 12, 24)))
    assert [e["id"] for e in timeoff.entries(conn)] == [a["id"], b["id"]]
    assert [e["id"] for e in timeoff.entries(conn, since=date(2027, 1, 1))] == [a["id"]]
    assert timeoff.entry_on(conn, date(2026, 12, 12))["id"] == b["id"]
    assert timeoff.entry_on(conn, date(2026, 12, 4))["id"] == a["id"]
    assert timeoff.entry_on(conn, date(2027, 1, 3)) is None
    assert timeoff.back_from(conn, date(2026, 12, 20), "run", 7)["id"] == a["id"]
    assert timeoff.back_from(conn, date(2026, 12, 20), "run", 2) is None
    assert timeoff.back_from(conn, date(2026, 12, 20), "swim", 7) is None


def test_update_and_delete_missing(conn):
    with pytest.raises(LookupError):
        timeoff.update(conn, 99, injury())
    with pytest.raises(LookupError):
        timeoff.delete(conn, 99)


def body(**over):
    return {"reason": "injury", "label": "Sore knee", "start": "2026-12-03",
            "restrictions": [{"category": "run", "until": "2026-12-17"}], **over}


def test_api_crud_and_validation(client, clock):
    r = client.post("/api/time-off", json=body(), headers=H)
    assert r.status_code == 201
    made = r.json()
    assert made["end"] == "2026-12-17" and made["restrictions"] == [{"category": "run", "until": "2026-12-17"}]
    assert [e["id"] for e in client.get("/api/time-off", headers=H).json()] == [made["id"]]

    r = client.patch(f"/api/time-off/{made['id']}", json=body(restrictions=[{"category": "run", "until": "2026-12-24"}]),
                     headers=H)
    assert r.status_code == 200 and r.json()["end"] == "2026-12-24"
    assert client.patch("/api/time-off/999", json=body(), headers=H).status_code == 404

    assert client.delete(f"/api/time-off/{made['id']}", headers=H).status_code == 204
    assert client.delete(f"/api/time-off/{made['id']}", headers=H).status_code == 404
    assert client.get("/api/time-off", headers=H).json() == []

    r = client.post("/api/time-off", json=body(restrictions=[{"category": "run", "until": "2026-12-01"}]), headers=H)
    assert r.status_code == 422 and "Every restriction must end on or after the start." in r.text
    assert client.post("/api/time-off", json=body(restrictions=[]), headers=H).status_code == 422
    dup = [{"category": "run", "until": "2026-12-10"}, {"category": "run", "until": "2026-12-11"}]
    assert client.post("/api/time-off", json=body(restrictions=dup), headers=H).status_code == 422
    assert client.post("/api/time-off", json=body()).status_code in (401, 403)


def test_api_lists_only_current_and_upcoming(client, clock):
    client.post("/api/time-off", json=body(start="2026-11-01", restrictions=[{"category": "run", "until": "2026-11-20"}]),
                headers=H)
    client.post("/api/time-off", json=body(), headers=H)
    assert [e["start"] for e in client.get("/api/time-off", headers=H).json()] == ["2026-12-03"]
