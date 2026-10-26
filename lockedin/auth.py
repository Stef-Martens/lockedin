"""Single-owner auth: Supabase JWTs for the app, a static bearer token for the Mac sync script."""

import hmac
from functools import lru_cache
from typing import Literal

import jwt
from fastapi import Header, HTTPException

from lockedin.config import get_settings

NOT_SIGNED_IN = "Not signed in."
MIN_SYNC_TOKEN_LEN = 16  # a placeholder like "change-me" must never unlock uploads


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, NOT_SIGNED_IN)
    return authorization[7:].strip()


def _owner_email(token: str) -> str:
    s = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not s.supabase_jwt_secret:
                raise HTTPException(401, NOT_SIGNED_IN)
            claims = jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        else:
            key = _jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")
    except (jwt.PyJWTError, jwt.PyJWKClientError) as e:
        raise HTTPException(401, NOT_SIGNED_IN) from e
    email = str(claims.get("email", "")).lower()
    if email != s.owner_email.lower():
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
