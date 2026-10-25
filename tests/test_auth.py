import time

import jwt
import pytest
from conftest import SYNC_TOKEN, owner_headers, token_for
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from lockedin import auth


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_me_requires_token(client):
    r = client.get("/api/me")
    assert r.status_code == 401 and r.json() == {"detail": "Not signed in."}


def test_me_rejects_other_email(client):
    assert client.get("/api/me", headers=bearer(token_for("x@example.com"))).status_code == 401


def test_me_rejects_bad_signature(client):
    t = token_for(secret="another-secret-another-secret-another-1")
    assert client.get("/api/me", headers=bearer(t)).status_code == 401


def test_me_rejects_expired_token(client):
    assert client.get("/api/me", headers=bearer(token_for(expires_in=-10))).status_code == 401


def test_me_ok_case_insensitive(client):
    r = client.get("/api/me", headers=bearer(token_for("Me@Example.COM")))
    assert r.status_code == 200 and r.json() == {"email": "me@example.com"}


def test_me_rejects_sync_token(client):
    assert client.get("/api/me", headers=bearer(SYNC_TOKEN)).status_code == 401


def test_owner_or_sync_accepts_both():
    assert auth.require_owner_or_sync(f"Bearer {SYNC_TOKEN}") == "sync"
    assert auth.require_owner_or_sync(owner_headers()["Authorization"]) == "owner"
    with pytest.raises(HTTPException) as e:
        auth.require_owner_or_sync("Bearer wrong")
    assert e.value.status_code == 401


def test_asymmetric_token_verified_via_jwks(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    now = int(time.time())
    token = jwt.encode({"email": "me@example.com", "aud": "authenticated", "exp": now + 60},
                       key, algorithm="ES256", headers={"kid": "k1"})

    class FakeJwks:
        def get_signing_key_from_jwt(self, t):
            return type("K", (), {"key": key.public_key()})()

    monkeypatch.setattr(auth, "_jwks_client", lambda: FakeJwks())
    assert auth.require_owner(f"Bearer {token}") == "me@example.com"


def test_weak_sync_token_is_never_accepted(monkeypatch):
    from lockedin.config import Settings, get_settings
    weak = Settings(**{**get_settings().__dict__, "sync_token": "change-me"})
    monkeypatch.setattr(auth, "get_settings", lambda: weak)
    with pytest.raises(HTTPException):
        auth.require_owner_or_sync("Bearer change-me")
