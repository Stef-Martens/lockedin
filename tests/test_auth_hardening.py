import logging
import time
from dataclasses import replace

import jwt
import pytest
from conftest import JWT_SECRET, OWNER_EMAIL
from fastapi import HTTPException

from lockedin import app as app_module
from lockedin import auth
from lockedin.config import get_settings

HOSTED = "https://abcd.supabase.co"
LOCAL_DEFAULT = "super-secret-jwt-token-with-at-least-32-characters-long"
OWNER_UUID = "6f1c9a52-8a4e-4c5e-9f57-0d5e2b7c1a11"


def token(secret=JWT_SECRET, url="http://127.0.0.1:54321", drop=(), **claims):
    now = int(time.time())
    body = {"sub": OWNER_UUID, "email": OWNER_EMAIL, "aud": "authenticated", "role": "authenticated",
            "iss": f"{url}/auth/v1", "iat": now, "exp": now + 3600, **claims}
    return jwt.encode({k: v for k, v in body.items() if k not in drop}, secret, algorithm="HS256")


@pytest.fixture
def settings(monkeypatch):
    def use(**changes):
        s = replace(get_settings(), **changes)
        monkeypatch.setattr(auth, "get_settings", lambda: s)
        return s
    auth._weak_secret_warning.cache_clear()
    return use


def ok(t: str) -> bool:
    try:
        return auth.require_owner(f"Bearer {t}") == OWNER_EMAIL
    except HTTPException as e:
        assert e.status_code == 401 and e.detail == "Not signed in."
        return False


def test_local_default_secret_still_works_on_the_local_stack(settings):
    settings(supabase_jwt_secret=LOCAL_DEFAULT)
    assert ok(token(LOCAL_DEFAULT))


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
@pytest.mark.parametrize("secret", [LOCAL_DEFAULT, "short-secret-0123456789"])
def test_known_or_short_secret_is_refused_outside_local(settings, secret, caplog):
    settings(supabase_url=HOSTED, supabase_jwt_secret=secret)
    with caplog.at_level(logging.WARNING, logger="lockedin.auth"):
        assert not ok(token(secret, url=HOSTED))
        assert not ok(token(secret, url=HOSTED))
    warnings = [r for r in caplog.records if "SUPABASE_JWT_SECRET" in r.getMessage()]
    assert len(warnings) == 1  # said once, not per request


def test_strong_secret_works_when_hosted(settings):
    strong = "x" * 40
    settings(supabase_url=HOSTED, supabase_jwt_secret=strong)
    assert ok(token(strong, url=HOSTED))


def test_issuer_must_be_this_project(settings):
    settings()
    assert not ok(token(url="https://other.supabase.co"))
    assert not ok(token(drop=("iss",)))


@pytest.mark.parametrize("claim", ["exp", "sub", "email"])
def test_required_claims(settings, claim):
    settings()
    assert ok(token())
    assert not ok(token(drop=(claim,)))


def test_owner_id_must_match_sub_when_set(settings):
    settings(owner_id=OWNER_UUID)
    assert ok(token())
    assert ok(token(sub=OWNER_UUID.upper()))
    assert not ok(token(sub="00000000-0000-0000-0000-000000000000"))


def test_jwks_client_has_a_timeout_and_caches_keys():
    auth._jwks_client.cache_clear()
    client = auth._jwks_client()
    auth._jwks_client.cache_clear()
    assert client.uri == "http://127.0.0.1:54321/auth/v1/.well-known/jwks.json"
    assert 0 < client.timeout <= 10 and client.jwk_set_cache is not None


def test_api_docs_only_on_the_local_stack():
    assert app_module.docs_urls(get_settings()) == {"docs_url": "/api/docs", "redoc_url": None,
                                                    "openapi_url": "/api/openapi.json"}
    assert app_module.docs_urls(replace(get_settings(), supabase_url=HOSTED)) == {
        "docs_url": None, "redoc_url": None, "openapi_url": None}


def test_is_local():
    s = get_settings()
    assert s.is_local
    assert not replace(s, supabase_url=HOSTED).is_local
    assert not replace(s, supabase_url="").is_local
    assert replace(s, supabase_url="http://localhost:54321").is_local
