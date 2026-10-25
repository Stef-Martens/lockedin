def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_body_too_large(client):
    r = client.post("/api/health", content=b"x" * 4_000_001)
    assert r.status_code == 413
    assert r.json() == {"detail": "File too large (max 4 MB)."}
