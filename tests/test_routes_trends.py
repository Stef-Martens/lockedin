from datetime import UTC, datetime

import pytest
from conftest import owner_headers, read

H = owner_headers()


@pytest.fixture(autouse=True)
def fixed_now(client):
    from lockedin.app import app
    from lockedin.routes.overview import get_now
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
    yield


def test_trends_for_each_sport(client):
    for sport in ("bike", "run", "swim"):
        assert client.get(f"/api/trends/{sport}", headers=H).status_code == 200
    assert client.get("/api/trends/gym", headers=H).status_code == 404


def test_gym_exercises_and_progress(client):
    client.post("/api/hevy/upload", files={"file": ("h.csv", read("hevy_sample.csv"))}, headers=H)
    ex = client.get("/api/gym/exercises", headers=H).json()
    bench = next(e for e in ex if e["name"] == "Bench Press (Barbell)")
    assert bench["mapped"] is True and {"key": "mid_lower_chest", "role": "primary"} in bench["muscles"]
    assert bench["sessions"] == 1 and bench["best_e1rm"] > 90
    p = client.get(f"/api/gym/exercises/{bench['id']}", headers=H).json()
    assert p["exercise"] == "Bench Press (Barbell)" and len(p["sessions"]) == 1
    assert len(client.get("/api/gym/volume?weeks=4", headers=H).json()) == 4


def test_tagging_an_unmapped_exercise(client):
    csv = b'title,start_time,exercise_title,weight_kg,reps\nX,"20 Oct 2099, 18:00",Zercher Squat,60,8\n'
    client.post("/api/hevy/upload", files={"file": ("x.csv", csv)}, headers=H)
    zercher = next(e for e in client.get("/api/gym/exercises", headers=H).json() if e["name"] == "Zercher Squat")
    assert zercher["mapped"] is False
    r = client.put(f"/api/gym/exercises/{zercher['id']}/muscles", headers=H,
                   json={"equipment": "barbell", "primary": ["quads"], "secondary": ["glutes", "abs"]})
    assert r.status_code == 200
    again = next(e for e in client.get("/api/gym/exercises", headers=H).json() if e["name"] == "Zercher Squat")
    assert again["mapped"] is True and {"key": "glutes", "role": "secondary"} in again["muscles"]


def test_tagging_rejects_unknown_muscles(client):
    csv = b'title,start_time,exercise_title,weight_kg,reps\nX,"20 Oct 2026, 18:00",Zercher Squat,60,8\n'
    client.post("/api/hevy/upload", files={"file": ("x.csv", csv)}, headers=H)
    zid = next(e["id"] for e in client.get("/api/gym/exercises", headers=H).json() if e["name"] == "Zercher Squat")
    bad = client.put(f"/api/gym/exercises/{zid}/muscles", headers=H, json={"equipment": "barbell", "primary": ["wings"]})
    assert bad.status_code == 422
    none = client.put(f"/api/gym/exercises/{zid}/muscles", headers=H, json={"equipment": "barbell", "primary": []})
    assert none.status_code == 422


def test_muscles_and_coverage(client):
    assert len(client.get("/api/muscles", headers=H).json()) == 20
    c = client.get("/api/gym/coverage", headers=H).json()
    assert set(c) == {"coverage", "unmapped"}


def test_requires_auth(client):
    for path in ("/api/trends/bike", "/api/gym/exercises", "/api/gym/coverage", "/api/muscles", "/api/gym/volume"):
        assert client.get(path).status_code == 401


def test_gym_suggestions_for_every_low_muscle(client):
    client.post("/api/hevy/upload", files={"file": ("h.csv", read("hevy_sample.csv"))}, headers=H)
    s = client.get("/api/gym/suggestions?limit=20", headers=H).json()
    assert len(s) > 3 and {"muscle_key", "exercise", "weight_kg", "dumbbell", "estimate", "reason"} <= set(s[0])
    assert "calves" in {x["muscle_key"] for x in s}
    assert client.get("/api/gym/suggestions").status_code == 401
