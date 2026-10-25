from conftest import SYNC_HEADERS, owner_headers, read


def upload(client, name, headers, source=None):
    data = {"source": source} if source else {}
    return client.post("/api/fit/upload", files={"file": (name, read(name))}, data=data, headers=headers)


def test_upload_with_sync_token_then_known(client):
    r = upload(client, "zwift_ride.fit", SYNC_HEADERS, source="zwift")
    assert r.status_code == 200 and r.json()["status"] == "imported"
    sha = r.json()["sha256"]
    k = client.post("/api/fit/known", json={"hashes": [sha, "0" * 64]}, headers=SYNC_HEADERS)
    assert k.json() == {"known": [sha]}


def test_upload_with_owner_token(client):
    r = upload(client, "watch_run.fit", owner_headers())
    assert r.json()["status"] == "imported"
    assert upload(client, "watch_run.fit", owner_headers()).json()["status"] == "duplicate"


def test_corrupt_upload_is_200_with_error(client):
    r = upload(client, "corrupt.fit", SYNC_HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "error" and r.json()["error"]


def test_upload_requires_auth(client):
    assert client.post("/api/fit/upload", files={"file": ("a.fit", b"x")}).status_code == 401
    assert client.post("/api/fit/known", json={"hashes": []}).status_code == 401


def test_bad_source_rejected(client):
    assert upload(client, "watch_run.fit", SYNC_HEADERS, source="strava").status_code == 422


def test_known_limits_batch_size(client):
    r = client.post("/api/fit/known", json={"hashes": ["a" * 64] * 501}, headers=SYNC_HEADERS)
    assert r.status_code == 422
