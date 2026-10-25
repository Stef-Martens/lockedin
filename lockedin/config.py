import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    supabase_url: str
    supabase_jwt_secret: str | None
    owner_email: str
    sync_token: str
    max_upload_bytes: int = 4_000_000


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_jwt_secret=os.environ.get("SUPABASE_JWT_SECRET") or None,
        owner_email=os.environ["OWNER_EMAIL"],
        sync_token=os.environ["SYNC_TOKEN"],
    )
