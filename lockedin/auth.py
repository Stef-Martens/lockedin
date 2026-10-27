"""Single-owner auth: Supabase JWTs for the app, static bearer tokens for the Mac sync script and the watch app."""

import hmac
import logging
from functools import lru_cache
from typing import Literal

import jwt
from fastapi import Header, HTTPException

from lockedin.config import Settings, get_settings

log = logging.getLogger(__name__)

NOT_SIGNED_IN = "Not signed in."
MIN_SYNC_TOKEN_LEN = 16  # a placeholder like "change-me" must never unlock uploads
# The local Supabase stack's public default: anyone could sign an owner token with it.
LOCAL_JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"
MIN_JWT_SECRET_BYTES = 32
REQUIRED_CLAIMS = ["exp", "sub", "email", "iss", "aud"]


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    # Keys cached 10 min (an unknown kid refetches); a slow auth server fails the request in 5 s, not 30.
    return jwt.PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True,
                           lifespan=600, timeout=5)


@lru_cache
def _weak_secret_warning() -> None:
    log.warning("SUPABASE_JWT_SECRET is the local default or shorter than %d bytes; HS256 tokens are refused. "
                "Set the project's real JWT secret, or clear it to use signing keys only.", MIN_JWT_SECRET_BYTES)


def _hs256_secret(s: Settings) -> str | None:
    """The legacy shared secret, unless it's guessable outside the local stack (then HS256 fails closed)."""
    secret = s.supabase_jwt_secret
    if secret and not s.is_local and (secret == LOCAL_JWT_SECRET or len(secret.encode()) < MIN_JWT_SECRET_BYTES):
        _weak_secret_warning()
        return None
    return secret


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, NOT_SIGNED_IN)
    return authorization[7:].strip()


def _owner_email(token: str) -> str:
    s = get_settings()
    checks = {"audience": "authenticated", "issuer": f"{s.supabase_url}/auth/v1",
              "options": {"require": REQUIRED_CLAIMS}}
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            secret = _hs256_secret(s)
            if not secret:
                raise HTTPException(401, NOT_SIGNED_IN)
            claims = jwt.decode(token, secret, algorithms=["HS256"], **checks)
        else:
            key = _jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"], **checks)
    except (jwt.PyJWTError, jwt.PyJWKClientError) as e:
        raise HTTPException(401, NOT_SIGNED_IN) from e
    email = str(claims["email"]).lower()
    if email != s.owner_email.lower() or (s.owner_id and str(claims["sub"]).lower() != s.owner_id):
        raise HTTPException(401, NOT_SIGNED_IN)
    return email


def require_owner(authorization: str | None = Header(None)) -> str:
    return _owner_email(_bearer(authorization))


def require_sync(authorization: str | None = Header(None)) -> Literal["sync"]:
    """Only the Mac sync's token, never an owner session."""
    token = _bearer(authorization)
    sync_token = get_settings().sync_token
    if len(sync_token) >= MIN_SYNC_TOKEN_LEN and hmac.compare_digest(token.encode(), sync_token.encode()):
        return "sync"
    raise HTTPException(401, NOT_SIGNED_IN)


def require_owner_or_sync(authorization: str | None = Header(None)) -> Literal["owner", "sync"]:
    token = _bearer(authorization)
    sync_token = get_settings().sync_token
    if len(sync_token) >= MIN_SYNC_TOKEN_LEN and hmac.compare_digest(token.encode(), sync_token.encode()):
        return "sync"
    _owner_email(token)
    return "owner"


def require_owner_or_watch(authorization: str | None = Header(None)) -> Literal["owner", "watch"]:
    """The owner, or the iPhone app's token (which unlocks only the watch feed)."""
    token = _bearer(authorization)
    watch_token = get_settings().watch_token
    if len(watch_token) >= MIN_SYNC_TOKEN_LEN and hmac.compare_digest(token.encode(), watch_token.encode()):
        return "watch"
    _owner_email(token)
    return "owner"
