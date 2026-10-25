import pytest
from conftest import SYNC_HEADERS, owner_headers, read

H = owner_headers()


def up_fit(client, name):
    return client.post("/api/fit/upload", files={"file": (name, read(name))}, headers=SYNC_HEADERS).json()["activity_id"]


def up_hevy(client):
    client.post("/api/hevy/upload", files={"file": ("h.csv", read("hevy_sample.csv"))}, headers=H)


@pytest.fixture
def loaded(client):
    ids = {n: up_fit(client, n) for n in ["zwift_ride.fit", "watch_indoor_cycle.fit", "watch_run.fit",
                                          "watch_pool_swim.fit", "watch_strength.fit", "watch_walk.fit"]}
    up_hevy(client)
    return ids


def test_list_newest_first_hides_walks_and_superseded(client, loaded):
    items = client.get("/api/activities", headers=H).json()["items"]
    titles = [(i["sport"], i["source"]) for i in items]
    # Legs (24th) · swim (23rd) · run (22nd) · Pull (22nd 16:30Z < run? no: run 07:00Z) · ride (20th 17:00Z) · Push (20th 16:00Z)
    assert titles == [("gym", "hevy"), ("swim", "healthfit"), ("gym", "hevy"), ("run", "healthfit"),
                      ("bike", "zwift"), ("gym", "hevy")]
    assert loaded["watch_walk.fit"] not in [i["id"] for i in items]
    assert loaded["watch_indoor_cycle.fit"] not in [i["id"] for i in items]


def test_list_flags_show_hidden(client, loaded):
    items = client.get("/api/activities?include_walks=true&include_superseded=true", headers=H).json()["items"]
    assert len(items) == 9


def test_sport_filter(client, loaded):
    items = client.get("/api/activities?sport=bike", headers=H).json()["items"]
    assert [i["id"] for i in items] == [loaded["zwift_ride.fit"]]


def test_pagination(client, loaded):
    page1 = client.get("/api/activities?limit=4", headers=H).json()
    assert len(page1["items"]) == 4 and page1["next_before"]
    page2 = client.get("/api/activities", params={"limit": 4, "before": page1["next_before"]}, headers=H).json()
    assert len(page2["items"]) == 2 and page2["next_before"] is None
    assert not {i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]}


def test_detail_streams_downsampled(client, loaded):
    d = client.get(f"/api/activities/{loaded['zwift_ride.fit']}", headers=H).json()
    s = d["streams"]
    assert len(s["t_offset"]) <= 1200 and len(s["power"]) == len(s["t_offset"])
    assert s["t_offset"][0] == 0 and s["power"][0] == pytest.approx(150)
    assert d["np"] and d["avg_power"] == 200


def test_detail_superseded_points_to_primary(client, loaded):
    d = client.get(f"/api/activities/{loaded['watch_indoor_cycle.fit']}", headers=H).json()
    assert d["superseded_by"] == loaded["zwift_ride.fit"]
    assert d["superseded_by_summary"]["source"] == "zwift"


def test_gym_detail_sets_in_order(client, loaded):
    gym = client.get("/api/activities?sport=gym", headers=H).json()["items"]
    push = next(i for i in gym if i["title"] == "Push Day")
    d = client.get(f"/api/activities/{push['id']}", headers=H).json()
    assert [(s["exercise"], s["set_index"]) for s in d["sets"]][:5] == [
        ("Bench Press (Barbell)", 0), ("Bench Press (Barbell)", 1), ("Bench Press (Barbell)", 2),
        ("Bench Press (Barbell)", 3), ("Lateral Raise (Dumbbell)", 0)]
    assert push["set_count"] == 8 and d["streams"] is None


def test_detail_404(client):
    assert client.get("/api/activities/999", headers=H).status_code == 404


def test_requires_auth(client):
    assert client.get("/api/activities").status_code == 401
    assert client.get("/api/activities/1").status_code == 401


def test_primary_detail_lists_the_watch_recordings_it_replaced(client, loaded):
    d = client.get(f"/api/activities/{loaded['zwift_ride.fit']}", headers=H).json()
    assert [x["id"] for x in d["duplicates"]] == [loaded["watch_indoor_cycle.fit"]]
    run = client.get(f"/api/activities/{loaded['watch_run.fit']}", headers=H).json()
    assert run["duplicates"] == []
