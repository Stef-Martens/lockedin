from conftest import SYNC_HEADERS, owner_headers

H = owner_headers()


def mac(client) -> dict:
    return client.get("/api/status", headers=H).json()["mac"]


def poll(client) -> str | None:
    r = client.post("/api/sync/mac/poll", headers=SYNC_HEADERS)
    assert r.status_code == 200
    return r.json()["check_requested_at"]


def test_status_mac_empty(client):
    assert set(mac(client).values()) == {None}


def test_run_report_sets_checked(client):
    r = client.post("/api/sync/mac/run", json={"uploaded": 2, "errors": 0}, headers=SYNC_HEADERS)
    assert r.status_code == 200
    m = mac(client)
    assert m["last_run_at"] and m["last_seen_at"]
    assert (m["last_run_uploaded"], m["last_run_errors"]) == (2, 0)


def test_poll_sets_seen(client):
    assert poll(client) is None
    m = mac(client)
    assert m["last_seen_at"] and m["last_run_at"] is None


def test_check_then_poll_then_answer(client):
    asked = client.post("/api/sync/mac/check", headers=H).json()["check_requested_at"]
    assert asked and poll(client) is not None
    requested = poll(client)
    client.post("/api/sync/mac/run", json={"uploaded": 1, "errors": 0, "answered": requested}, headers=SYNC_HEADERS)
    m = mac(client)
    assert m["check_done_at"] and m["check_uploaded"] == 1
    assert poll(client) is None


def test_newer_request_survives_older_answer(client):
    client.post("/api/sync/mac/check", headers=H)
    first = poll(client)
    client.post("/api/sync/mac/check", headers=H)
    second = poll(client)
    assert second != first
    client.post("/api/sync/mac/run", json={"uploaded": 0, "errors": 0, "answered": first}, headers=SYNC_HEADERS)
    assert poll(client) == second
    assert mac(client)["check_done_at"] is None


def test_auth(client):
    assert client.post("/api/sync/mac/poll", headers=H).status_code == 401
    assert client.post("/api/sync/mac/run", json={"uploaded": 0, "errors": 0}, headers=H).status_code == 401
    assert client.post("/api/sync/mac/check", headers=SYNC_HEADERS).status_code == 401
    for path in ("poll", "run", "check"):
        assert client.post(f"/api/sync/mac/{path}").status_code == 401


def test_run_rejects_negative(client):
    r = client.post("/api/sync/mac/run", json={"uploaded": -1, "errors": 0}, headers=SYNC_HEADERS)
    assert r.status_code == 422
