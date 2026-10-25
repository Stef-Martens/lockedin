from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.pool import NullPool

from lockedin.config import get_settings


def make_engine(url: str) -> Engine:
    # Serverless + Supabase transaction pooler: no client-side pool, no prepared statements.
    return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


def get_conn() -> Iterator[Connection]:
    with get_engine().begin() as conn:
        yield conn
