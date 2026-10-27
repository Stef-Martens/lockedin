import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from dotenv import load_dotenv

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    supabase_url: str
    supabase_jwt_secret: str | None
    owner_email: str
    sync_token: str
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    max_upload_bytes: int = 4_000_000
    owner_id: str | None = None
    coach_daily_budget_usd: float = 5.0

    @property
    def is_local(self) -> bool:
        """Running against the local Supabase stack (anything else is treated as production)."""
        return urlsplit(self.supabase_url).hostname in LOCAL_HOSTS


def _budget(raw: str | None) -> float:
    try:
        return max(float(raw), 0.0) if raw else 5.0
    except ValueError:
        return 5.0


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET") or None,
        owner_email=os.environ["OWNER_EMAIL"],
        sync_token=os.environ["SYNC_TOKEN"],
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.environ.get("ANTHROPIC_MODEL") or "claude-opus-5-5",
        owner_id=(os.environ.get("OWNER_ID") or "").strip().lower() or None,
        coach_daily_budget_usd=_budget(os.environ.get("COACH_DAILY_BUDGET_USD")),
    )
