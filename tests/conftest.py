import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
SAMPLES = ROOT / "samples"

TEST_ADMIN_URL = os.environ.get(
    "TEST_ADMIN_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
)
TEST_DB = "lockedin_test"

OWNER_EMAIL = "me@example.com"
JWT_SECRET = "test-secret-test-secret-test-secret-123"
SYNC_TOKEN = "sync-test-token"

SEED_SQL = """
insert into profile (id) values (1);
insert into measurement_types (name, unit, kind) values
  ('Weight','kg','weight'),('Chest','cm','tape'),('Left arm','cm','tape'),('Right arm','cm','tape'),
  ('Waist','cm','tape'),('Hips','cm','tape'),('Left thigh','cm','tape'),('Right thigh','cm','tape'),
  ('Shoulders','cm','tape');
"""

# Settings must point at the test DB before lockedin modules read them.
os.environ.update(
    DATABASE_URL=str(make_url(TEST_ADMIN_URL).set(database=TEST_DB).render_as_string(hide_password=False)),
    SUPABASE_URL="http://127.0.0.1:54321",
    SUPABASE_JWT_SECRET=JWT_SECRET,
    OWNER_EMAIL=OWNER_EMAIL,
    SYNC_TOKEN=SYNC_TOKEN,
)


def read(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


@pytest.fixture(scope="session")
def engine():
    admin = create_engine(TEST_ADMIN_URL, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"drop database if exists {TEST_DB} with (force)"))
        c.execute(text(f"create database {TEST_DB}"))
    eng = create_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    with eng.begin() as c:
        # Supabase roles exist on the local stack; create stand-ins elsewhere.
        c.exec_driver_sql(
            "do $$ begin "
            "if not exists (select from pg_roles where rolname='anon') then create role anon; end if; "
            "if not exists (select from pg_roles where rolname='authenticated') then create role authenticated; end if; "
            "end $$;"
        )
        for m in MIGRATIONS:
            # Raw driver call: migration SQL contains literal % (format('%I')), no bind params.
            c.connection.driver_connection.execute(m.read_text())
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"drop database if exists {TEST_DB} with (force)"))
    admin.dispose()


@pytest.fixture
def clean_db(engine):
    with engine.begin() as c:
        tables = c.execute(text("select tablename from pg_tables where schemaname='public'")).scalars().all()
        c.exec_driver_sql(f"truncate {', '.join(tables)} restart identity cascade")
        c.exec_driver_sql(SEED_SQL)
    return engine


@pytest.fixture
def conn(clean_db):
    with clean_db.begin() as c:
        yield c


@pytest.fixture
def client(clean_db):
    from fastapi.testclient import TestClient

    from lockedin import db
    from lockedin.app import app

    def _conn():
        with clean_db.begin() as c:
            yield c

    app.dependency_overrides[db.get_conn] = _conn
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()
