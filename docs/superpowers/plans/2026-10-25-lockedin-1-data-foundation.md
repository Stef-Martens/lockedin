# LockedIn Plan 1 — Data Foundation & Imports

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deployable app where the owner logs in, their Zwift rides and Apple Watch workouts (HealthFit FIT files) sync automatically from the Mac, Hevy CSVs upload without duplicates, and they can browse activities and log body measurements.

**Architecture:** One FastAPI app (`lockedin/` package) served as a Vercel Python function at `/api/*`, talking to Supabase Postgres through SQLAlchemy Core. All data access goes through FastAPI, which verifies Supabase JWTs. RLS is on with no policies, so PostgREST exposes nothing. A stdlib-only Mac script uploads new FIT files from two folders. A Vite React app in `web/` handles login, uploads, activities and body measurements. Plan 2 (focus engine + dashboard) and Plan 3 (AI coach) build on this.

**Tech Stack:** Python 3.12+ (FastAPI, SQLAlchemy 2 Core, psycopg 3, fitdecode, PyJWT, python-multipart, python-dotenv, tzdata; dev: pytest, httpx, fit-tool), Supabase CLI (local stack in Docker), React 18 + Vite + TypeScript, react-router-dom, @supabase/supabase-js, Recharts, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-25-lockedin-design.md`

## Global Constraints

- Single user. Every data endpoint requires the owner's Supabase JWT (email must equal `OWNER_EMAIL`). FIT sync endpoints accept that JWT **or** `Authorization: Bearer <SYNC_TOKEN>`, compared with `hmac.compare_digest`.
- RLS enabled on every table, no policies; `anon`/`authenticated` privileges revoked.
- Never send `ANTHROPIC_API_KEY`, `SYNC_TOKEN`, DB URL or service-role key to the frontend. The frontend only gets `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- Store all timestamps as UTC `timestamptz`. Local time is Europe/Brussels. Weeks run Monday–Sunday in Brussels.
- Metric units: metres in the DB, km/kg/cm in the UI.
- Request bodies are capped at 4,000,000 bytes, which keeps them under Vercel's ~4.5 MB limit. Anything larger returns HTTP 413 with a clear message.
- Strava is never integrated.
- UI copy is neutral and encouraging. Errors explain what to do next.
- Before writing any chart code, load the `dataviz` skill.
- Commit after each task, with a message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Hevy export in pounds or with a BOM/CRLF.** A CSV with a `weight_lbs` column (instead of `weight_kg`), a UTF-8 BOM and `\r\n` line endings must import with weights converted to kg (×0.45359237). → test in Task 6.
2. **Zwift file still being written, or a corrupt FIT.** The sync script must ignore files modified in the last 60 s. A truncated or corrupt FIT must come back as `status="error"` (not a 500). It is retried if uploaded again, and is not reported as known. → tests in Tasks 4 and 5.
3. **Apple Watch strength workout during a Hevy session.** A HealthFit `training` workout that overlaps a Hevy workout by more than 50% must be superseded by the Hevy one, like the Zwift rule. Otherwise every gym session counts twice. *(Extends spec 5.3 to Hevy; same intent as the anti-goal "double counting".)* → test in Task 4.
4. **macOS privacy block on `~/Documents` or iCloud Drive.** When launchd's python can't read the folder, the script must log a clear message telling the owner to grant Full Disk Access, keep going with the other folder, and not crash. → test in Task 5.
5. **DST and midnight in Brussels.** A Hevy time like `29 Mar 2026, 02:30` (doesn't exist) or `25 Oct 2026, 02:30` (happens twice) must parse without crashing (use `fold=0`). A Sunday 23:30 ride must land in that week, not the next. → tests in Tasks 1 and 6.

---

## File Structure

```
pyproject.toml              deps, pytest config
requirements.txt            runtime deps for Vercel
.python-version             3.12 (Vercel runtime)
vercel.json                 build, rewrites, function config, region fra1
Makefile                    dev, test, samples, owner
.env.example
README.md
scripts/dev.sh              starts supabase (if needed) + uvicorn + vite
scripts/create_owner.py     creates the single auth user via Supabase admin API
scripts/make_samples.py     writes synthetic FIT samples
supabase/config.toml        from `supabase init`; enable_signup = false
supabase/migrations/20261025000001_core.sql
api/index.py                Vercel entry: `from lockedin.app import app`
lockedin/config.py          Settings from env
lockedin/db.py              engine + connection dependency
lockedin/timeutil.py        Brussels tz helpers
lockedin/auth.py            require_owner, require_owner_or_sync
lockedin/app.py             FastAPI app + routers + body-size guard
lockedin/fit/parse.py       FIT bytes -> ParsedFit
lockedin/fit/metrics.py     NP, best average power, IF/TSS
lockedin/fitness.py         ftp_at()
lockedin/fit/importer.py    import_fit(), known_hashes()
lockedin/dedupe.py          resolve_overlaps() + HR merge
lockedin/hevy/parse.py      CSV -> HevyParseResult
lockedin/hevy/importer.py   upsert workouts/sets
lockedin/routes/{fit,hevy,activities,body,status}.py
sync/fit_sync.py            Mac uploader (stdlib only)
sync/com.lockedin.fitsync.plist.template
sync/install.sh, sync/uninstall.sh
samples/                    generated .fit files + hevy CSVs
tests/                      pytest
web/                        Vite React app
```

---

### Task 1: Backend skeleton, schema, test database

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.python-version`, `.env.example`, `Makefile`, `scripts/dev.sh`, `supabase/config.toml` (via `supabase init`), `supabase/migrations/20261025000001_core.sql`, `lockedin/__init__.py`, `lockedin/config.py`, `lockedin/db.py`, `lockedin/timeutil.py`, `lockedin/app.py`, `api/index.py`
- Test: `tests/conftest.py`, `tests/test_schema.py`, `tests/test_timeutil.py`, `tests/test_app.py`

**Interfaces:**
- Produces:
  - `Settings` (frozen dataclass): `database_url: str, supabase_url: str, supabase_jwt_secret: str | None, owner_email: str, sync_token: str, max_upload_bytes: int = 4_000_000`; `get_settings() -> Settings` (lru_cached; `load_dotenv()` first).
  - `make_engine(url: str) -> Engine`: `postgresql+psycopg`, `NullPool`, `connect_args={"prepare_threshold": None}` (Supabase transaction pooler).
  - `get_conn() -> Iterator[Connection]`: FastAPI dependency yielding a connection inside `engine.begin()`.
  - `TZ = ZoneInfo("Europe/Brussels")`; `week_start(dt: datetime) -> date` (Monday, Brussels); `parse_local(s: str, formats: Sequence[str]) -> datetime` (naive local string → aware UTC, `fold=0`; nonexistent times shifted forward by the gap).
  - `app` (FastAPI) with `GET /api/health -> {"ok": true}`. Middleware rejects `Content-Length > max_upload_bytes` with 413 `{"detail": "File too large (max 4 MB)."}`.
  - Test fixtures: `engine` (session scope: creates DB `lockedin_test` on `TEST_ADMIN_URL`, default `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres`, applies every `supabase/migrations/*.sql` in order, drops the DB at the end), `conn` (per test: truncates all public tables `RESTART IDENTITY CASCADE`, re-runs the seed inserts, yields a connection), `client` (TestClient with `get_conn` overridden to the test engine and settings overridden: `owner_email="me@example.com"`, `supabase_jwt_secret="test-secret-test-secret-test-secret-123"`, `sync_token="sync-test-token"`).

- [ ] **Step 1: Init tooling.** `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`; `supabase init`; set `[auth] enable_signup = false` in `supabase/config.toml`; `supabase start`.
- [ ] **Step 2: Write failing tests**

```python
# tests/test_schema.py
TABLES = {"profile","activities","activity_streams","fit_files","exercises",
          "gym_workouts","gym_sets","measurement_types","measurements","import_log"}
def test_all_tables_exist_with_rls(conn):
    rows = conn.execute(text("select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and relkind='r'")).all()
    assert {r[0] for r in rows} == TABLES
    assert all(r[1] for r in rows)
def test_seeds(conn):
    assert conn.execute(text("select count(*) from profile")).scalar() == 1
    names = conn.execute(text("select name from measurement_types order by id")).scalars().all()
    assert names == ["Weight","Chest","Left arm","Right arm","Waist","Hips","Left thigh","Right thigh","Shoulders"]

# tests/test_timeutil.py
def test_week_start_sunday_late_evening_brussels():
    assert week_start(datetime(2026,10,25,22,30,tzinfo=UTC)) == date(2026,10,19)  # Sun 23:30 local
def test_week_start_monday_early_local():
    assert week_start(datetime(2026,10,25,23,30,tzinfo=UTC)) == date(2026,10,26)  # Mon 00:30 local
def test_parse_local_ambiguous_and_nonexistent():
    assert parse_local("25 Oct 2026, 02:30", ["%d %b %Y, %H:%M"]) == datetime(2026,10,25,0,30,tzinfo=UTC)
    assert parse_local("29 Mar 2026, 02:30", ["%d %b %Y, %H:%M"]) == datetime(2026,3,29,1,30,tzinfo=UTC)

# tests/test_app.py
def test_health(client): assert client.get("/api/health").json() == {"ok": True}
def test_body_too_large(client):
    r = client.post("/api/health", content=b"x"*4_000_001)
    assert r.status_code == 413
```

- [ ] **Step 3: Run** `make test` → FAIL (modules/tables missing).
- [ ] **Step 4: Write the migration.** This is the schema; copy it exactly:

```sql
create table profile (
  id smallint primary key default 1 check (id = 1),
  date_of_birth date, height_cm real, sex text check (sex in ('male','female')),
  max_hr_override smallint, ftp_override smallint, resting_hr_override smallint,
  updated_at timestamptz not null default now());
insert into profile (id) values (1);

create table activities (
  id bigint generated always as identity primary key,
  source text not null check (source in ('zwift','healthfit','hevy')),
  source_ref text not null,
  sport text not null check (sport in ('bike','run','swim','gym','other')),
  sub_type text,
  start_at timestamptz not null, end_at timestamptz not null,
  duration_s integer not null, moving_s integer,
  distance_m real, elevation_m real,
  avg_hr smallint, max_hr smallint, calories integer,
  avg_power smallint, max_power smallint, avg_cadence smallint,
  np real, if_ real, tss real, best_20m_power real,
  avg_pace_s_per_km real, swim_pace_s_per_100m real,
  swim_lengths integer, swim_strokes integer, pool_length_m real,
  effort_class text,
  hr_merged_from bigint references activities(id) on delete set null,
  superseded_by bigint references activities(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (source, source_ref));
create index activities_start_idx on activities (start_at desc);
create index activities_sport_start_idx on activities (sport, start_at desc);

create table activity_streams (
  activity_id bigint primary key references activities(id) on delete cascade,
  t_offset integer[] not null, power smallint[], hr smallint[], cadence smallint[],
  speed real[], altitude real[], distance real[]);

create table fit_files (
  sha256 text primary key, filename text not null, source text,
  uploaded_at timestamptz not null default now(),
  activity_id bigint references activities(id) on delete set null,
  parse_status text not null check (parse_status in ('ok','error')), error text);

create table exercises (
  id bigint generated always as identity primary key,
  name text not null unique, is_bodyweight boolean not null default false);

create table gym_workouts (
  activity_id bigint primary key references activities(id) on delete cascade,
  hevy_key text not null unique, title text not null, description text,
  content_hash text not null);

create table gym_sets (
  id bigint generated always as identity primary key,
  workout_id bigint not null references gym_workouts(activity_id) on delete cascade,
  exercise_id bigint not null references exercises(id),
  exercise_order smallint not null, set_index smallint not null,
  set_type text not null default 'normal',
  weight_kg real, reps smallint, distance_km real, duration_s integer, rpe real,
  superset_id text, notes text, e1rm real);
create index gym_sets_exercise_idx on gym_sets (exercise_id);

create table measurement_types (
  id bigint generated always as identity primary key,
  name text not null unique, unit text not null,
  kind text not null check (kind in ('weight','tape','other')));
insert into measurement_types (name, unit, kind) values
  ('Weight','kg','weight'),('Chest','cm','tape'),('Left arm','cm','tape'),('Right arm','cm','tape'),
  ('Waist','cm','tape'),('Hips','cm','tape'),('Left thigh','cm','tape'),('Right thigh','cm','tape'),
  ('Shoulders','cm','tape');

create table measurements (
  id bigint generated always as identity primary key,
  type_id bigint not null references measurement_types(id) on delete cascade,
  measured_on date not null, value real not null check (value > 0),
  source text not null default 'manual', note text,
  created_at timestamptz not null default now());

create table import_log (
  id bigint generated always as identity primary key,
  source text not null, at timestamptz not null default now(), summary jsonb not null);

do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
  end loop; end $$;
revoke all on all tables in schema public from anon, authenticated;
```

  The `conn` fixture's seed re-run executes the two `insert` statements above (keep them in `tests/conftest.py` as `SEED_SQL`).
- [ ] **Step 5: Implement** `config.py`, `db.py`, `timeutil.py`, `app.py`, `api/index.py`. `.env.example` lists: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY` (scripts only), `OWNER_EMAIL`, `SYNC_TOKEN`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `ANTHROPIC_API_KEY` (Plan 3), `ANTHROPIC_MODEL=claude-opus-5-5` (Plan 3), with local Supabase defaults and comments. Makefile targets: `install`, `dev` (→ `scripts/dev.sh`: `supabase status || supabase start`, then uvicorn `lockedin.app:app --reload --port 8000` and `npm --prefix web run dev`, `trap` kills both), `test` (`.venv/bin/pytest -q`), `samples`, `owner`.
- [ ] **Step 6: Run** `make test` → PASS.
- [ ] **Step 7: Commit** `feat: backend skeleton, core schema with RLS, test database`.

---

### Task 2: Authentication

**Files:**
- Create: `lockedin/auth.py`, `scripts/create_owner.py`
- Modify: `lockedin/app.py` (add `GET /api/me`)
- Test: `tests/test_auth.py`; add helper `owner_headers()` / `token_for(email)` in `tests/conftest.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces:
  - `require_owner(authorization: str = Header(None)) -> str` (returns email). It verifies the JWT. For `alg == "HS256"` it uses `supabase_jwt_secret` and audience `"authenticated"`. Otherwise it uses `PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")`, cached at module level. It rejects a missing or invalid token, or one whose `email` claim isn't `owner_email` (case-insensitive), with 401 `{"detail": "Not signed in."}`.
  - `require_owner_or_sync(authorization: str = Header(None)) -> Literal["owner","sync"]`.
  - `GET /api/me -> {"email": str}` (owner).
  - `scripts/create_owner.py --email E --password P`: POSTs `{SUPABASE_URL}/auth/v1/admin/users` with the service-role key, `email_confirm: true`. Wired to `make owner`.

- [ ] **Step 1: Write failing tests:** `test_me_requires_token` (no header → 401), `test_me_rejects_other_email` (valid HS256 token for `x@example.com` → 401), `test_me_rejects_bad_signature`, `test_me_ok` (`me@example.com`, any case → 200 `{"email": "me@example.com"}`), `test_expired_token_rejected`, `test_sync_token_accepted_only_where_allowed` (a dummy route in the test using `require_owner_or_sync` returns `"sync"` for `Bearer sync-test-token`; `/api/me` with the sync token → 401).
- [ ] **Step 2: Run** `pytest tests/test_auth.py -v` → FAIL.
- [ ] **Step 3: Implement** `auth.py`, `/api/me`, `create_owner.py`.
- [ ] **Step 4: Run** → PASS. Manual check: `make owner EMAIL=... PASSWORD=...` against local Supabase prints the new user id.
- [ ] **Step 5: Commit** `feat: owner-only auth with Supabase JWT and sync token`.

---

### Task 3: FIT parsing, power metrics, sample files

**Files:**
- Create: `lockedin/fit/__init__.py`, `lockedin/fit/parse.py`, `lockedin/fit/metrics.py`, `scripts/make_samples.py`, `samples/*.fit` (generated, committed)
- Test: `tests/test_fit_parse.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `@dataclass Streams: t_offset: list[int]; power: list[int|None]; hr: list[int|None]; cadence: list[int|None]; speed: list[float|None]; altitude: list[float|None]; distance: list[float|None]`
  - `@dataclass ParsedFit: sport: Literal["bike","run","swim","other"]; sub_type: str | None` (`f"{fit_sport}/{fit_sub_sport}"`, e.g. `"cycling/virtual_activity"`, `"walking/generic"`, `"training/strength_training"`); `manufacturer: str | None; start_at: datetime; end_at: datetime; duration_s: int; moving_s: int | None; distance_m, elevation_m: float | None; avg_hr, max_hr, avg_power, max_power, avg_cadence, calories: int | None; pool_length_m: float | None; swim_lengths, swim_strokes: int | None; streams: Streams`
  - `class FitParseError(Exception)`; `parse_fit(data: bytes) -> ParsedFit`. Uses `fitdecode.FitReader(io.BytesIO(data))`. Summary values come from the `session` message, falling back to values computed from `record` messages. Swim lengths/strokes come from `length` messages with `length_type == "active"`. FIT sport mapping: `cycling`→bike, `running`→run, `swimming`→swim, everything else→other. Raises `FitParseError` on decode errors or when there's no `record`/`session` data.
  - `normalized_power(power, t_offset) -> float | None`: resample to 1 Hz (forward-fill gaps ≤5 s, 0 beyond), 30 s rolling mean, then the 4th-power mean to the power 0.25. Returns None if there are fewer than 30 s of power or all values are None/0.
  - `best_avg_power(power, t_offset, window_s: int) -> float | None` (same 1 Hz resample; None if the ride is shorter than the window).
  - `training_stress(duration_s: int, np_: float, ftp: float) -> tuple[float, float]` → `(if_, tss)` where `if_ = np_/ftp`, `tss = duration_s * np_ * if_ / (ftp * 3600) * 100`.
  - `scripts/make_samples.py` (uses `fit-tool`) writes:
    - `samples/zwift_ride.fit`: manufacturer zwift, cycling/virtual_activity, 2026-10-20 17:00:00Z, 3600 s, 1 Hz, power 30 min at 150 W then 30 min at 250 W, HR 130→160, cadence 85, 30 km.
    - `samples/zwift_ride_no_hr.fit`: same, no HR.
    - `samples/watch_indoor_cycle.fit`: manufacturer apple/development, cycling/indoor_cycling, 2026-10-20 16:58:00Z, 3700 s, HR every 5 s.
    - `samples/watch_run.fit`: running, 2026-10-22 07:00:00Z, 2700 s, 8.0 km, HR.
    - `samples/watch_pool_swim.fit`: swimming/lap_swimming, pool 25 m, 40 active lengths, 18 strokes each, 2026-10-23 18:00:00Z, 1800 s.
    - `samples/watch_strength.fit`: training/strength_training, 2026-10-24 17:05:00Z, 3000 s.
    - `samples/watch_walk.fit`: walking, 2026-10-24 12:00:00Z, 1200 s.
    - `samples/corrupt.fit`: the first 200 bytes of `zwift_ride.fit`.

- [ ] **Step 1: Generate samples** with `make samples` (target runs `scripts/make_samples.py`). Commit the files.
- [ ] **Step 2: Write failing tests**

```python
def test_np_constant(): assert normalized_power([200]*3600, list(range(3600))) == pytest.approx(200, abs=0.5)
def test_np_two_blocks(): p=[100]*1800+[300]*1800; assert normalized_power(p, list(range(3600))) == pytest.approx(253, abs=3)
def test_np_too_short(): assert normalized_power([200]*20, list(range(20))) is None
def test_tss(): assert training_stress(3600, 200, 250) == pytest.approx((0.8, 64.0))
def test_best_20m(): p=[150]*1800+[250]*1800; assert best_avg_power(p, list(range(3600)), 1200) == pytest.approx(250)
def test_parse_zwift_ride():
    f = parse_fit(read("zwift_ride.fit"))
    assert (f.sport, f.manufacturer, f.duration_s) == ("bike", "zwift", 3600)
    assert f.start_at == datetime(2026,10,20,17,0,tzinfo=UTC)
    assert f.avg_power == pytest.approx(200, abs=2) and f.max_power == 250
    assert f.distance_m == pytest.approx(30000, rel=0.01) and len(f.streams.power) == 3600
def test_parse_pool_swim():
    f = parse_fit(read("watch_pool_swim.fit"))
    assert (f.sport, f.pool_length_m, f.swim_lengths, f.swim_strokes) == ("swim", 25.0, 40, 720)
def test_parse_walk_and_strength_subtypes():
    assert parse_fit(read("watch_walk.fit")).sub_type.startswith("walking")
    assert parse_fit(read("watch_strength.fit")).sub_type.startswith("training")
def test_parse_corrupt_raises():
    with pytest.raises(FitParseError): parse_fit(read("corrupt.fit"))
```

- [ ] **Step 3: Run** `pytest tests/test_fit_parse.py tests/test_metrics.py -v` → FAIL.
- [ ] **Step 4: Implement** `metrics.py` and `parse.py`.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat: FIT parsing, NP/TSS metrics and synthetic samples`.

---

### Task 4: FIT import, overlap dedupe, HR merge, FIT endpoints

**Files:**
- Create: `lockedin/fitness.py`, `lockedin/fit/importer.py`, `lockedin/dedupe.py`, `lockedin/routes/__init__.py`, `lockedin/routes/fit.py`
- Modify: `lockedin/app.py` (include router)
- Test: `tests/test_fit_import.py`, `tests/test_dedupe.py`, `tests/test_routes_fit.py`

**Interfaces:**
- Consumes: `parse_fit`, metrics (Task 3); `require_owner_or_sync` (Task 2); `get_conn` (Task 1).
- Produces:
  - `ftp_at(conn, on: datetime) -> float | None`: returns `profile.ftp_override` if set. Otherwise 0.95 × max `best_20m_power` over bike activities with `start_at` in `(on − 90 days, on]` that aren't superseded. None if neither exists.
  - `@dataclass FitImportResult: status: Literal["imported","duplicate","error"]; sha256: str; activity_id: int | None; error: str | None`
  - `import_fit(conn, data: bytes, filename: str, source_hint: Literal["zwift","healthfit"] | None) -> FitImportResult`.
    - Hashes the bytes with SHA-256. An existing `fit_files` row with `parse_status='ok'` → `duplicate`.
    - Parses the file. A parse error upserts `fit_files` with `parse_status='error'` and returns `error`.
    - The source is the hint if given, else `"zwift"` when the manufacturer is `zwift`, else `"healthfit"`. `source_ref` is the sha256.
    - Inserts the activity, its streams, `best_20m_power` (bike), `np`, then `if_`/`tss` via `ftp_at(start_at)`. Also `avg_pace_s_per_km` (run, from moving or elapsed time) and `swim_pace_s_per_100m` (swim).
    - Upserts `fit_files` as ok, calls `resolve_overlaps(conn, activity_id)`, and writes `import_log` (source = the activity source).
  - `known_hashes(conn, hashes: list[str]) -> set[str]` (ok rows only).
  - `resolve_overlaps(conn, activity_id: int) -> None`:
    - Overlap means `max(0, min(end) − max(start)) > 0.5 × min(duration)`.
    - A healthfit activity overlapping a zwift or hevy activity gets `superseded_by` set to that activity. Prefer zwift when the watch activity is a bike.
    - A new zwift or hevy activity marks every overlapping, not-yet-superseded healthfit activity as superseded by it.
    - **HR merge**, after superseding: if the primary is zwift and its `avg_hr` is null while the superseded watch activity has HR, copy `avg_hr`/`max_hr` and set `hr_merged_from`. Then build `activity_streams.hr` for the ride: for each ride second, take the nearest watch HR sample within ±5 s by absolute time, else None.
  - `POST /api/fit/known` body `{"hashes": [str]}` (≤500) → `{"known": [str]}`; `POST /api/fit/upload` multipart `file` + optional form `source` → `FitImportResult` as JSON. Both use `require_owner_or_sync`.

- [ ] **Step 1: Write failing tests**

```python
def test_import_then_duplicate(conn):
    r1 = import_fit(conn, read("zwift_ride.fit"), "a.fit", "zwift"); assert r1.status == "imported"
    r2 = import_fit(conn, read("zwift_ride.fit"), "renamed.fit", None); assert r2.status == "duplicate"
    assert count(conn, "activities") == 1
def test_corrupt_is_error_and_retryable(conn):
    r = import_fit(conn, read("corrupt.fit"), "c.fit", "zwift"); assert r.status == "error" and r.error
    assert known_hashes(conn, [r.sha256]) == set()
def test_source_detected_from_manufacturer(conn):
    a = import_fit(conn, read("zwift_ride.fit"), "x.fit", None); assert source_of(conn, a.activity_id) == "zwift"
    b = import_fit(conn, read("watch_run.fit"), "y.fit", None); assert source_of(conn, b.activity_id) == "healthfit"
def test_tss_with_override(conn):
    conn.execute(text("update profile set ftp_override=250"))
    a = import_fit(conn, read("zwift_ride.fit"), "x.fit", "zwift")
    row = get_activity(conn, a.activity_id); assert row.np == pytest.approx(217, abs=3) and row.tss is not None
def test_run_pace(conn):
    a = import_fit(conn, read("watch_run.fit"), "r.fit", "healthfit")
    assert get_activity(conn, a.activity_id).avg_pace_s_per_km == pytest.approx(337.5, abs=1)
# dedupe — both arrival orders
@pytest.mark.parametrize("order", [("zwift_ride.fit","watch_indoor_cycle.fit"), ("watch_indoor_cycle.fit","zwift_ride.fit")])
def test_watch_superseded_by_zwift(conn, order):
    ids = {n: import_fit(conn, read(n), n, None).activity_id for n in order}
    assert superseded_by(conn, ids["watch_indoor_cycle.fit"]) == ids["zwift_ride.fit"]
    assert superseded_by(conn, ids["zwift_ride.fit"]) is None
@pytest.mark.parametrize("order", [0, 1])
def test_hr_merged_when_zwift_has_no_hr(conn, order):
    names = ["zwift_ride_no_hr.fit", "watch_indoor_cycle.fit"][::(1 if order == 0 else -1)]
    ids = {n: import_fit(conn, read(n), n, None).activity_id for n in names}
    ride = get_activity(conn, ids["zwift_ride_no_hr.fit"])
    assert ride.avg_hr is not None and ride.hr_merged_from == ids["watch_indoor_cycle.fit"]
    assert sum(h is not None for h in stream(conn, ride.id).hr) > 3000
def test_non_overlapping_untouched(conn):
    import_fit(conn, read("zwift_ride.fit"), "z", None); r = import_fit(conn, read("watch_run.fit"), "r", None)
    assert superseded_by(conn, r.activity_id) is None
# routes
def test_known_and_upload_with_sync_token(client): ...  # upload zwift_ride via sync token → imported; /known returns its hash
def test_upload_requires_auth(client): assert client.post("/api/fit/upload", files={"file": ("a.fit", b"x")}).status_code == 401
```

  Add `test_watch_strength_superseded_by_hevy` in Task 6. It needs the Hevy importer, which also calls `resolve_overlaps`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `fitness.py`, `importer.py`, `dedupe.py`, `routes/fit.py`.
- [ ] **Step 4: Run** `make test` → PASS.
- [ ] **Step 5: Commit** `feat: FIT import with hash dedupe, Zwift/Watch overlap and HR merge`.

---

### Task 5: Mac sync script + launchd agent

**Files:**
- Create: `sync/fit_sync.py`, `sync/com.lockedin.fitsync.plist.template`, `sync/install.sh`, `sync/uninstall.sh`
- Test: `tests/test_fit_sync.py`

**Interfaces:**
- Consumes: `POST /api/fit/known`, `POST /api/fit/upload` (Task 4).
- Produces (stdlib only, runs under `/usr/bin/python3`):
  - Config from `~/.config/lockedin/sync.env` (KEY=VALUE), overridable by env: `LOCKEDIN_API` (e.g. `https://lockedin.vercel.app`), `SYNC_TOKEN`, `ZWIFT_ACTIVITIES_DIR` (default `~/Documents/Zwift/Activities`), `HEALTHFIT_DIR` (no default; path confirmed when the owner installs HealthFit).
  - `candidate_files(folders: list[tuple[Path, str]], now: float, min_age_s: int = 60) -> tuple[list[tuple[Path, str]], list[str]]` returns (files, warnings). It takes `*.fit` case-insensitive and skips names starting with `.`, `*.icloud` placeholders, files with `mtime > now − min_age_s`, and files over 4,000,000 bytes (adds a warning). A missing folder gives a warning. `PermissionError` gives the warning `"Can't read <folder>: give Full Disk Access to python3 (System Settings → Privacy & Security → Full Disk Access). See README."`, and the script continues.
  - `@dataclass SyncReport: uploaded: int; duplicates: int; errors: list[str]; warnings: list[str]`
  - `sync_once(cfg: dict, now: float, http: Callable[[str, str, bytes, dict], tuple[int, bytes]] = urllib_http) -> SyncReport`: hashes candidates, asks `/known` in batches of 500, uploads unknown files one at a time (multipart built by hand, form `source` = folder label `zwift`/`healthfit`). On a network error it logs and stops the run, so the next trigger retries.
  - `main()` logs one summary line per run to stdout (launchd sends it to `~/Library/Logs/lockedin-sync.log`). Exit code is 0 even with warnings.
  - The plist template has `WatchPaths` for both folders, `StartInterval` 3600 and `RunAtLoad` true. `install.sh` fills in the paths, writes `~/Library/LaunchAgents/com.lockedin.fitsync.plist`, and runs `launchctl bootstrap gui/$UID`. `uninstall.sh` reverses this.

- [ ] **Step 1: Write failing tests** (temp dirs + fake `http`): `test_skips_recent_hidden_icloud_and_large`, `test_missing_and_unreadable_folder_warns_but_continues` (monkeypatch `Path.iterdir` to raise `PermissionError` for one folder, and assert the other folder's file is still a candidate and the warning text mentions "Full Disk Access"), `test_uploads_only_unknown` (fake `/known` returns one of two hashes → exactly one upload, with `source=zwift` in the body), `test_network_error_stops_run`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS. Manual: with `make dev` running and `LOCKEDIN_API=http://127.0.0.1:8000`, point `ZWIFT_ACTIVITIES_DIR` at `samples/`. Run `python3 sync/fit_sync.py` and check the output reads `uploaded N`. A second run reports `uploaded 0`.
- [ ] **Step 5: Commit** `feat: Mac FIT sync script with launchd agent`.

---

### Task 6: Hevy CSV import

**Files:**
- Create: `lockedin/hevy/__init__.py`, `lockedin/hevy/parse.py`, `lockedin/hevy/importer.py`, `lockedin/routes/hevy.py`, `samples/hevy_sample.csv`, `samples/hevy_reordered_lbs.csv`
- Modify: `lockedin/app.py`
- Test: `tests/test_hevy.py`

**Interfaces:**
- Consumes: `parse_local` (Task 1), `resolve_overlaps` (Task 4), `require_owner`.
- Produces:
  - `@dataclass HevySet: exercise_title: str; exercise_order: int; set_index: int; set_type: str; weight_kg: float | None; reps: int | None; distance_km: float | None; duration_s: int | None; rpe: float | None; superset_id: str | None; notes: str | None`
  - `@dataclass HevyWorkout: title: str; description: str | None; start_at: datetime; end_at: datetime; sets: list[HevySet]`
  - `@dataclass HevyParseResult: workouts: list[HevyWorkout]; skipped: list[tuple[int, str]]` (1-based CSV row, reason)
  - `parse_hevy_csv(text: str) -> HevyParseResult`.
    - Strips a BOM and accepts CRLF.
    - Normalises headers (lowercase, trim, spaces → `_`).
    - Required columns: `title`, `start_time`, `exercise_title`. If any is missing, raises `ValueError("Missing column(s): ...")`.
    - Optional columns are read when present: `end_time, description, exercise_notes, superset_id, set_index, set_type, weight_kg | weight_lbs (×0.45359237), reps, distance_km | distance_miles (×1.609344), duration_seconds, rpe`. Unknown columns are ignored.
    - Dates are parsed with formats `["%d %b %Y, %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]`.
    - Rows are grouped by `(title, start_time)`. `exercise_order` is the order of first appearance within the workout.
    - A missing `end_time` falls back to `start_time + 1 h`.
    - Rows with unparseable numbers are skipped with a reason.
  - `@dataclass HevyImportResult: new: int; updated: int; unchanged: int; skipped: list[tuple[int, str]]`
  - `import_hevy(conn, parsed: HevyParseResult) -> HevyImportResult`.
    - `hevy_key = f"{start_at.isoformat()}|{title}"`. `content_hash` = sha256 of the canonical JSON of the sets.
    - If the key is new, insert the activity (`source='hevy'`, `sport='gym'`, `source_ref=hevy_key`), the `gym_workouts` row and the sets.
    - If the key exists with the same hash, count it as unchanged. With a different hash, update the activity times, delete and re-insert the sets, and count it as updated.
    - Exercises are upserted by name.
    - `e1rm = weight_kg * (1 + reps/30)` for non-warmup sets with weight > 0 and reps ≥ 1 (reps == 1 → weight).
    - Calls `resolve_overlaps` for each new or updated workout and writes `import_log`. Workouts absent from the CSV are never deleted.
  - `POST /api/hevy/upload` (owner) multipart `file` → `HevyImportResult` JSON. A `ValueError` becomes 422 with the message.

- [ ] **Step 1: Write the sample CSVs.** `hevy_sample.csv` uses the spec header order. It has 3 workouts, including warmup sets, a superset pair, a bodyweight exercise (empty weight) and an extra unknown column. One workout runs 2026-10-24 19:00–19:55 Brussels, overlapping `watch_strength.fit`. `hevy_reordered_lbs.csv` has a BOM, CRLF, reordered columns, `weight_lbs`, and one workout at `25 Oct 2026, 02:30`.
- [ ] **Step 2: Write failing tests:** `test_parse_sample_counts` (3 workouts, expected set counts), `test_lbs_bom_crlf_reordered` (100 lbs → 45.36 kg), `test_missing_required_column_raises`, `test_reimport_is_idempotent` (import twice → second `{new:0, updated:0, unchanged:3}`, row counts unchanged), `test_edit_propagates` (change one weight → `updated == 1`, set replaced), `test_absent_workout_kept`, `test_e1rm` (100 kg × 5 → 116.67; warmup → None), `test_watch_strength_superseded_by_hevy` (both arrival orders), `test_upload_route` (owner token → 200 JSON; no token → 401).
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** `make test` → PASS.
- [ ] **Step 6: Commit** `feat: Hevy CSV import with tolerant parsing and idempotent re-import`.

---

### Task 7: Activities, body measurements, status endpoints

**Files:**
- Create: `lockedin/routes/activities.py`, `lockedin/routes/body.py`, `lockedin/routes/status.py`
- Modify: `lockedin/app.py`
- Test: `tests/test_routes_activities.py`, `tests/test_routes_body.py`, `tests/test_routes_status.py`

**Interfaces:**
- Consumes: owner auth, tables from Task 1.
- Produces (all owner-only, Pydantic response models in each route file):
  - `GET /api/activities?sport=bike|run|swim|gym|other&include_walks=false&include_superseded=false&limit=30&before=<iso>` → `{"items": [ActivitySummary], "next_before": str | null}`. `ActivitySummary` holds the `activities` columns used in the UI (id, source, sport, sub_type, start_at, duration_s, distance_m, avg_hr, avg_power, np, tss, avg_pace_s_per_km, swim_pace_s_per_100m, calories, superseded_by). Walks are `sub_type LIKE 'walking%'`.
  - `GET /api/activities/{id}` → `ActivityDetail` = summary + all columns + `streams` downsampled to ≤ 1,200 points (bucket mean; `t_offset` takes each bucket's first value) + `sets` (gym: exercise name, order, set_index, set_type, weight_kg, reps, rpe, e1rm, ordered) + `superseded_by_summary` / `hr_merged_from`. 404 if not found.
  - `GET /api/profile`, `PUT /api/profile` (fields from the `profile` table; ranges validated: height 100–250 cm, max_hr 120–230, ftp 50–600).
  - `GET /api/measurement-types`, `POST /api/measurement-types {name, unit, kind}` (409 on duplicate name).
  - `GET /api/measurements?type_id=` → list ordered by `measured_on`. `POST /api/measurements {type_id, measured_on, value, note?}`. `DELETE /api/measurements/{id}`.
  - `GET /api/status` → `{"zwift": {"last_import_at", "count"}, "healthfit": {...}, "hevy": {...}, "last_tape_measurement_on": date | null}`.

- [ ] **Step 1: Write failing tests:** list newest first; sport filter; walks and superseded rows hidden by default and shown with their flags; pagination via `before`; detail streams ≤1200 points for the 3600 s sample; gym detail returns sets in order; profile validation (height 300 → 422); measurement CRUD; duplicate type → 409; status after one import of each source; all routes → 401 without a token.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make test` → PASS.
- [ ] **Step 5: Commit** `feat: activities, profile, measurements and status API`.

---

### Task 8: Frontend: login, import, activities, body

**Files:**
- Create: `web/` via `npm create vite@latest web -- --template react-ts`, then `web/vite.config.ts` (`envDir: '..'`, dev proxy `/api` → `http://127.0.0.1:8000`), `web/src/lib/supabase.ts`, `web/src/lib/api.ts`, `web/src/lib/format.ts`, `web/src/styles.css`, `web/src/components/Layout.tsx`, `web/src/pages/{Login,Import,Activities,ActivityDetail,Body}.tsx`, `web/src/App.tsx`
- Test: `web/src/lib/format.test.ts` (Vitest)

**Interfaces:**
- Consumes: every endpoint from Tasks 2, 4, 6 and 7.
- Produces:
  - `supabase` client (persistSession true, autoRefreshToken true).
  - `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` adds `Authorization: Bearer <access_token>`. On 401 it signs out and redirects to `/login`. On other errors it throws `ApiError {status, detail}`.
  - `uploadFile<T>(path: string, file: File, fields?: Record<string,string>): Promise<T>`.
  - `formatDuration(s: number): string`, `formatPace(sPerKm: number): string`, `formatSwimPace(sPer100: number): string`, `formatDistance(m: number, sport: Sport): string`, `type Sport = "bike"|"run"|"swim"|"gym"|"other"`.
  - Routes: `/login`, `/` (redirect to `/activities` until Plan 2 adds Overview), `/activities`, `/activities/:id`, `/import`, `/body`.
  - `Layout`: top bar on desktop. On phone width (<640 px) it becomes a bottom tab bar (Activities, Import, Body; Plan 2 adds Overview/sport tabs).
  - Pages:
    - **Import:** a FIT multi-file drop zone that uploads sequentially and shows a result per file (imported / already imported / error + message). A Hevy CSV upload shows the new/updated/unchanged/skipped counts. A "Last synced" panel comes from `/api/status`.
    - **Activities:** sport filter chips and a list showing date (Brussels), sport, duration, distance, key metric (bike NP or avg power, run pace, swim pace/100 m, gym sets count), with "Load more".
    - **ActivityDetail:** summary tiles. Charts (Recharts) of power/HR/cadence for rides, HR/pace for runs, swim summary, and a gym sets table grouped by exercise. Notes "Duplicate of Zwift ride" / "Heart rate from Apple Watch" link to the related activity.
    - **Body:** profile form; quick-add measurement (type select, date defaults to today, value); a small line chart per type that has data; "add measurement type" form.
  - `styles.css`: color tokens on `:root`, a dark-mode override via `prefers-color-scheme`, 16 px side gutters, no horizontal scroll at 375 px.

- [ ] **Step 1: Write failing test**

```ts
expect(formatDuration(3725)).toBe("1:02:05"); expect(formatDuration(605)).toBe("10:05")
expect(formatPace(300)).toBe("5:00 /km"); expect(formatSwimPace(125)).toBe("2:05 /100m")
expect(formatDistance(12345, "bike")).toBe("12.3 km"); expect(formatDistance(1500, "swim")).toBe("1500 m")
```

- [ ] **Step 2: Run** `npm --prefix web test -- --run` → FAIL.
- [ ] **Step 3: Implement** `format.ts`, then the rest. Load the `dataviz` skill before the ActivityDetail and Body charts.
- [ ] **Step 4: Verify.** Run `npm --prefix web test -- --run` → PASS and `npm --prefix web run build` → no type errors. Then run `make dev`, create the owner with `make owner`, and log in. Upload every `samples/*.fit` except `corrupt.fit`, then both Hevy CSVs. Check the following, and also at 375 px width in browser devtools:
  - the activity list hides the watch indoor cycle, watch strength and walk
  - the ride detail shows power/HR charts
  - uploading `corrupt.fit` shows a friendly error
  - re-uploading the Hevy CSV shows `3 unchanged`
  - a measurement can be added and its chart appears
- [ ] **Step 5: Commit** `feat: web app with login, imports, activities and body measurements`.

---

### Task 9: Vercel deployment config + README

**Files:**
- Create: `vercel.json`, `README.md`
- Modify: `requirements.txt` (check it matches the runtime deps in `pyproject.toml`)

**Interfaces:**
- Produces `vercel.json`:

```json
{
  "buildCommand": "npm --prefix web ci && npm --prefix web run build",
  "outputDirectory": "web/dist",
  "regions": ["fra1"],
  "functions": { "api/index.py": { "maxDuration": 60,
    "excludeFiles": "{web/**,tests/**,samples/**,supabase/**,sync/**,docs/**,scripts/**,.venv/**}" } },
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```

- README sections, each with exact commands:
  1. What it is.
  2. Local setup: Docker, Supabase CLI, `make install`, `cp .env.example .env`, `make dev`, `make owner`.
  3. Hosted setup: create a Supabase project in the **EU (Frankfurt)** region. Run `supabase link` + `supabase db push`. Turn off sign-ups (Auth → Providers → Email → disable "Allow new users to sign up"). Create the owner with `make owner` using the hosted keys. Use the **transaction pooler** URL (port 6543) as `DATABASE_URL` with the `postgresql+psycopg://` scheme. Note that free projects pause after about a week without activity, and how to un-pause.
  4. Vercel: import the repo and set env vars (list). Use `npx vercel` for CLI deploys.
  5. Mac sync: create `~/.config/lockedin/sync.env` and run `sync/install.sh`. **Grant Full Disk Access to python3** (exact System Settings path; find the binary with `python3 -c 'import sys; print(sys.executable)'`). Check `~/Library/Logs/lockedin-sync.log`. Uninstall steps.
  6. HealthFit on iPhone: install it, allow Health access, enable auto-export of workouts as **FIT** to **iCloud Drive**, export past workouts in bulk for history, and find the folder on the Mac to set `HEALTHFIT_DIR`. Mark the exact menu names "to verify once installed".
  7. Hevy: Settings → Export & Import data → Export workouts → upload the CSV on the Import page. Always upload the full export; it's safe to repeat.
  8. Troubleshooting: 413 file too large, sync log warnings, 401 after a password change.
- [ ] **Step 1:** Write `vercel.json` and the README.
- [ ] **Step 2: Verify.** Run `make test` → all pass. Run `npm --prefix web run build` → ok. Run `python -c "import api.index"` with production-like env → imports without error.
- [ ] **Step 3: Commit** `docs: README and Vercel deployment config`.
- [ ] **Step 4: Deploy with the owner (needs their accounts).** Create the Supabase project, push migrations, deploy to Vercel, and install the sync agent. Check: log in on the phone over mobile data, and see a Zwift ride from the Mac appear after it's saved.

---

## Next plans

- **Plan 2 — Focus engine & dashboard** (spec 5.5, 5.6): muscles + exercise mapping seed, zones, effort classes, muscle coverage, suggested add-on exercises with weights, trends, wins, plateaus, streak, comeback; Overview / Bike / Run / Swim / Gym pages.
- **Plan 3 — AI coach** (spec 5.7): read-only DB role, tools, goals + check-ins, streaming chat panel.
