# LockedIn — personal training tracker & coach

Design document, 2026-10-25. Single user (the owner). Metric units, timezone Europe/Brussels.

## 1. Intent

The owner trains across four sports: bike (Zwift on a Mac), run and swim (Apple Watch → Apple Health), and gym (Hevy app). Today that data is scattered over three apps. LockedIn pulls it into one place and answers two questions every time it's opened:

1. **Am I improving?** Trends per sport, not just totals.
2. **What should I focus on next?** Concrete suggestions: "you've barely trained triceps / rear delts — do these exercises at this weight", "you haven't done a long easy run in 3 weeks", "all your rides are the same medium effort — add an interval ride".

The owner also wants to log body measurements (weight, tape measurements like chest and arms) to see physical progress over time.

The owner's own words on when they'd stop using it: *when they stop training, or when results aren't good.* So the app has to be most useful exactly in those moments — pull them back in, never make them feel bad.

They want to use it **on their phone at the gym** (to see today's suggested workout), which is why it is hosted rather than local-only.

## 2. Goals

- One place for all training data from Zwift, Apple Health and Hevy, with dedupe so re-imports and overlapping recordings never double-count.
- Dashboard: regular stats plus improvement trends per sport.
- Calculated "focus" facts (no AI needed): muscle-group coverage for gym, effort mix for run/bike, trends, recent wins, plateaus.
- Body measurements log with charts.
- AI coach (chat) that reads the data through safe tools and turns the facts into concrete workouts, remembers the owner's goals, and checks in on them periodically.
- Works well at phone width; usable at the gym.

## 3. Non-goals

- Strava integration of any kind (its API terms forbid AI use). Do not add it.
- Multi-user support, sign-up, sharing.
- Push notifications / reminders outside the app.
- Writing data back to Hevy, Zwift or Apple Health.
- A native mobile app (the responsive web app is enough).
- Workout logging inside LockedIn during the gym session (Hevy stays the logger).

## 4. Anti-goals (failure even if it "works")

- **Guilt UI.** No walls of red, no "−80% vs last month" after a gap. After a break the app shows when they last trained and offers a small, easy way back in.
- **Unsafe suggestions.** Suggested weights for unfamiliar exercises must be conservative; better too light than too heavy.
- **Data exposure.** Health data is on the internet now. Nothing may be readable without login; the Supabase auto-generated REST API must not expose tables to the anon key.
- **Leaking the AI key** to the browser, or letting the AI write to the database beyond the one narrow goals tool.
- **Double counting** a Zwift ride that the Apple Watch also recorded.

## 5. Decisions

Marked **(owner)** where the owner decided, **(my call)** where I chose and the owner hasn't explicitly confirmed.

### 5.1 Hosting & stack

- **(owner)** Hosted: **Vercel** (frontend + Python API) and **Supabase** (Postgres + Auth). This replaces the original local SQLite / LAN (0.0.0.0) plan.
- **(owner)** Backend: Python, FastAPI, `fitdecode` for FIT files. Runs as a Vercel Python function (single FastAPI app mounted under `/api`).
- **(owner)** Frontend: React + Vite + TypeScript, Recharts.
- **(owner)** Config via `.env` with a `.env.example`; README with setup steps.
- **(my call)** Database access with SQLAlchemy Core + psycopg 3, connecting through Supabase's **transaction pooler** (serverless-friendly; disable prepared statements). Schema managed as SQL migrations in `supabase/migrations/` (Supabase CLI).
- **(my call)** Regions: Supabase in EU (Frankfurt), Vercel functions pinned to `fra1`.
- **(my call)** Local development: Supabase CLI local stack (Docker is installed) + Vite dev server + uvicorn, started with one command (`make dev`). Deploy with Vercel (Git integration or `vercel` CLI).
- All timestamps stored as UTC `timestamptz`; weeks are Monday–Sunday in Europe/Brussels for every weekly aggregate.

### 5.2 Security

- **(my call)** Login with **Supabase Auth, email + password**, long-lived session (magic links are awkward on a phone at the gym). Sign-ups disabled in Supabase; the backend additionally checks the JWT's user id/email against `OWNER_EMAIL`.
- The frontend only talks to Supabase for **auth**. All data goes through the FastAPI backend, which verifies the Supabase JWT on every request.
- **Row Level Security enabled on every table with no policies** for `anon`/`authenticated`, so Supabase's PostgREST API exposes nothing. The backend connects with its own DB role.
- Machine endpoints (Apple Health ingest, Zwift sync) use separate **static bearer tokens** from env (`HEALTH_INGEST_TOKEN`, `SYNC_TOKEN`), compared in constant time.
- `ANTHROPIC_API_KEY` lives only in backend env (Vercel env vars / local `.env`), never sent to the frontend.

### 5.3 Data sources

**Zwift (bike).** A hosted app can't read `~/Documents/Zwift/Activities`, so:
- **(my call)** A small **Mac sync script** (`sync/zwift_sync.py`, stdlib + `requests` only), run by a **launchd agent** using `WatchPaths` on the Zwift folder plus a periodic fallback (e.g. hourly). It hashes each `.fit` (SHA-256), asks the API which hashes are already known, and uploads only new files. Folder path from `ZWIFT_ACTIVITIES_DIR`. README documents installing/uninstalling the launchd agent.
- A manual **"Upload FIT"** button in the UI as a fallback (multi-file).
- Server dedupes by file hash regardless of path.
- Summary stored: start time, duration (elapsed + moving), distance, elevation gain, avg/max power, avg/max HR, avg cadence, calories, **NP, IF, TSS** (computed from per-second power and the FTP in effect at ride date).
- Per-second data in a separate table. **(my call)** Stored as **one row per activity with columnar arrays** (time offset, power, HR, cadence, speed, altitude, distance) rather than one row per second, to stay well inside Supabase's free 500 MB (a 1-hour ride is ~100 KB this way vs. ~0.5 MB+ as rows).
- Zwift FIT files are typically well under Vercel's ~4.5 MB request limit; the script skips/flags any file above it.

**Hevy (gym).** Manual CSV upload in the UI.
- Expected export header (as of 2026): `title, start_time, end_time, description, exercise_title, superset_id, exercise_notes, set_index, set_type, weight_kg, reps, distance_km, duration_seconds, rpe`. Builder must confirm against a real export and parse **by column name**, tolerating extra, missing or reordered columns; unknown columns are ignored, missing optional ones become null.
- Dates are Hevy's local-time strings (e.g. `25 Oct 2026, 18:30`), interpreted as Europe/Brussels.
- **Dedupe:** a workout is identified by `(start_time, title)`. Re-importing an existing workout **replaces its exercises and sets** (so edits in Hevy propagate). Workouts missing from a newer export are **not** deleted (my call — safer with partial exports).
- Upload result shows counts: new workouts, updated workouts, unchanged, rows skipped (with reasons).

**Apple Health (run, swim, others)** via the iOS app **Health Auto Export** (third-party, by Lybron Sobers; not Apple). Apple offers no web access to Health data, so an iOS app is required. Two supported paths:
- **Premium** (€1.99/month, €7.99/year or €29.99 lifetime; 7-day trial): REST API automation, sends in the background. The main path.
- **Basic** (€2.99 one-time): manual export only. The owner exports a JSON file now and then and uploads it in the UI (same path as the history backfill below).

Both paths must work. Pricing from the Belgian App Store, 2026-10-25.
- `POST /api/ingest/health`, bearer `HEALTH_INGEST_TOKEN`. Accepts Health Auto Export's JSON (`{"data": {"workouts": [...], "metrics": [...]}}`, format version 2). Builder must verify field names against the app's current docs and a real sample.
- Every payload stored raw (`jsonb`) with received-at timestamp, then parsed. **(my call)** Identical payloads are deduped by SHA-256; raw payloads older than 90 days that parsed successfully are pruned, so overlapping syncs don't fill the 500 MB.
- **History backfill (my call):** the UI accepts a manual Health Auto Export JSON export file (e.g. one per year). The browser parses it and posts workouts in batches under ~3 MB to an authenticated endpoint that uses the same parser/upsert. README explains how to make these exports. Apple Health's full `export.zip` is not supported.
- Workouts parsed: external id (HAE workout `id` if present, else hash of type+start+end), type (running, swimming, cycling, walking, other…), start/end, duration, distance, avg/max HR, pace, active calories, elevation; for swims: lap length, laps, stroke count, pool vs open water where available. Per-workout HR samples stored if included.
- Metrics: **body mass** (weight) imported into the measurements table if present; other metrics (resting HR, VO₂max) stored if present, displayed later. Not required.
- Re-sent workouts upsert by external id (no duplicates).
- Keep payloads small: README tells the owner to configure frequent syncs over a short date range and to **turn off route/GPS data** (not needed and it bloats payloads past Vercel's request limit).
- **Overlap dedupe (owner):** a Health workout that overlaps in time with a Zwift ride by more than 50% of the shorter one is marked `superseded_by` that ride and excluded from all stats. Applied whichever arrives first (re-checked on every Zwift and Health import). Superseded rows remain visible in the activity detail as "duplicate of Zwift ride".
- **HR merge (my call):** if the Zwift ride has no HR data (no strap paired in Zwift), the superseded Health workout's HR (avg/max and samples, aligned by timestamp) is copied onto the Zwift ride and its stream. Works in both arrival orders.
- **Walks (my call):** walking workouts are stored and listed (sport `other`, sub_type walking) but excluded from totals, streaks and the comeback check, since the Watch records many casual walks. Other workout types (hiking, rowing, HIIT, etc.) count as `other` sessions.

### 5.4 Data model (Postgres)

Sketch; builder may adjust names/types.

- `profile` (single row): date_of_birth, height_cm, sex (optional, for formulas), max_hr_override, ftp_override, resting_hr_override, created/updated.
- `activities`: id, source (`zwift|health|hevy`), sport (`bike|run|swim|gym|other`), sub_type (raw type), start_at, end_at, duration_s, moving_s, distance_m, elevation_m, avg_hr, max_hr, calories, avg_power, max_power, avg_cadence, np, if_, tss, avg_pace_s_per_km, swim_pace_s_per_100m, swim_laps, swim_strokes, pool_length_m, effort_class, superseded_by (fk), source_ref (file hash / HAE id / hevy key), unique(source, source_ref).
- `activity_streams`: activity_id (pk/fk), t_offset int[], power int[], hr int[], cadence int[], speed real[], altitude real[], distance real[].
- `fit_files`: sha256 (pk), filename, uploaded_at, activity_id, parse_status, error.
- `health_payloads`: id, received_at, payload jsonb, parse_status, error, counts.
- `gym_workouts`: id (= activities.id), hevy_key (start_time+title), title, description, start_at, end_at.
- `gym_sets`: id, workout_id, exercise_id, exercise_order, set_index, set_type (normal/warmup/dropset/failure), weight_kg, reps, distance_km, duration_s, rpe, superset_id, notes, e1rm (computed).
- `exercises`: id, name (as in Hevy, unique), equipment, is_bodyweight, mapped (bool).
- `muscles`: id, name, group (e.g. `shoulders`→ front/side/rear delt). Taxonomy (my call): upper chest, mid/lower chest, front delt, side delt, rear delt, triceps, biceps, forearms, lats, upper back/traps, rhomboids/mid back, lower back, abs, obliques, glutes, quads, hamstrings, adductors, abductors, calves.
- `exercise_muscles`: exercise_id, muscle_id, role (`primary` = 1 set credit, `secondary` = 0.5).
- `measurement_types`: id, name, unit, kind (`weight|tape|other`); seeded with weight, chest, left arm, right arm, waist, hips, left thigh, right thigh, shoulders; owner can add more.
- `measurements`: id, type_id, measured_at (date), value, source (`manual|health`), note.
- `goals`: id, text, sport/area (optional), target (free text or structured metric+value), status (`active|achieved|dropped`), created_at, updated_at, source (`coach|manual`).
- `coach_conversations` / `coach_messages`: for chat history; `coach_state`: last_goal_checkin_at.

### 5.5 Calculated facts ("focus" engine, no AI)

A backend module computes these on request (cache allowed). They power the dashboard **and** are exposed to the coach as a tool.

- **Zones.** Max HR = override, else highest HR seen in last 12 months if plausible, else 220 − age. FTP = override, else 95% of best 20-min power (from streams) in last 90 days. HR zones as % of max HR (5 zones); power zones Coggan-style from FTP. Exact cut-offs left to the builder; documented in code.
- **Effort class per run/ride:** `easy`, `steady`, `hard` (intervals/threshold), `long`. Based on time-in-zone (streams or HR samples when available, else avg HR/IF) and duration relative to the owner's own recent median (long ≈ ≥1.5× median and mostly easy). Swims: simple classification by pace vs recent median.
- **Effort mix:** last 4 weeks per sport vs a simple target mix (e.g. mostly easy, one hard, one long per week). Flags what's missing ("no long run in 3 weeks", "all rides steady").
- **Muscle coverage:** weekly sets per muscle (primary 1, secondary 0.5; warmups excluded), last 4 weeks vs a target range (e.g. ~10–20 sets/week for major muscles; builder may tune). Flags under-trained muscles. Exercises without a muscle mapping are listed for the owner to tag in the UI.
- **Suggested exercises & weights (owner: add-on list, not full sessions):** v1 does not build complete workouts. It suggests 1–3 exercises to **add** to whatever the owner already planned. Full session planning is the coach's job in v2. For an under-trained muscle, pick 1–3 exercises from the seed library that target it (preferring ones the owner already does). Weight: from the owner's recent e1RM (Epley) for that exercise at a target rep range (e.g. 8–12, RPE ~8). For an exercise never done: estimate from a related exercise via a seed ratio table, then multiply by ~0.8 and mark it "estimate — start light". Bodyweight exercises suggest reps.
- **Trends:** bike efficiency (NP/avg HR) and 20-min best power over time; run pace and pace-at-HR (aerobic efficiency) over time; swim pace per 100 m; gym e1RM per exercise; body measurements.
- **Recent wins:** PRs (e1RM, best 20-min power, longest run/ride, fastest pace over common distances, swim pace), improved efficiency, best consistency vs same period last year.
- **Plateaus:** an exercise/metric with no improvement for ≥6 weeks while still being trained → one specific suggestion (e.g. change rep range, add a set, swap variation). Rule-based; the coach can elaborate.
- **Consistency:** week streak = consecutive weeks with ≥2 sessions (any sport). No daily streaks.
- **Comeback state:** if no session in ≥7 days, overview leads with "last trained X days ago" + one easy restart suggestion instead of comparisons.

### 5.6 Dashboard (v1)

Mobile-first, clean, simple. Navigation: Overview · Activities · Bike · Run · Swim · Gym · Body · Coach (v2).

- **Overview:** comeback banner (when applicable) · "Focus this week" card (top 1–3 calculated suggestions, e.g. "add cable pushdowns 3×10 at 20 kg — triceps are low this month", "add one long easy run") · recent wins strip · this week / this month totals per sport (time, distance, sessions) · week streak · weekly volume chart stacked by sport (bike, run, swim, gym), toggle 12/26 weeks (gym measured in time) · "time to measure" note when last tape measurement > 4 weeks old.
- **Activities:** list with sport filter, newest first, paging; tap → detail (summary + charts from streams: power/HR/cadence for rides, HR/pace for runs; swim laps; gym exercises & sets).
- **Bike:** power and HR trend, FTP estimate, efficiency, effort mix.
- **Run:** pace and HR trend, pace-at-HR, weekly distance, effort mix.
- **Swim:** weekly distance, pace per 100 m.
- **Gym:** muscle coverage (sets per muscle, under-trained highlighted), per-exercise progress (best set / e1RM over time), weekly volume (kg × reps), unmapped-exercise tagging.
- **Body:** profile form; add measurement (date, type, value); chart per measurement type; manage measurement types.
- **Data/settings:** Hevy CSV upload, FIT upload, last sync times per source (Zwift script, Health), import history with errors.

Tone of all copy: neutral-to-encouraging. Declines shown factually, never in alarming red; always paired with what to do.

### 5.7 AI coach (v2, after v1 works)

- Chat panel (Coach tab; fits on phone). Backend calls the Claude API with the Anthropic Python SDK and tool use; responses streamed to the frontend. Model configurable via `ANTHROPIC_MODEL`, default the latest most capable model (`claude-opus-5-5`).
- **Tools:**
  - `get_schema` — curated description of tables/columns/meaning (units, zones, conventions).
  - `run_sql` — **read-only**: executed as a dedicated Postgres role with `SELECT` only on data tables (no access to raw payloads, auth, or coach tables beyond goals), `default_transaction_read_only = on`, short `statement_timeout`, single statement only, row cap (e.g. 200) on results.
  - `get_focus_facts` — the calculated facts from 5.5 (coverage, effort mix, trends, wins, plateaus, suggested weights).
  - `get_goals` and `save_goal` — the only write path. The system prompt instructs the coach to propose a goal change and only call `save_goal` after the owner agrees in chat.
- **Goal check-ins (owner):** goals persist in the DB and are read every conversation. The coach asks about goals on first use, then again roughly every 4–6 weeks (tracked via `last_goal_checkin_at`) or sooner when it notices a shift (a sport stopped, a goal reached).
- **Coaching style:** concrete next sessions ("Thursday: 3×10 cable pushdowns at 20 kg…", "Saturday: 90 min easy ride, zone 2"), restart-small after gaps, highlight wins, treat plateaus as problems to solve. No medical advice beyond common sense; suggest seeing a professional for pain/injury.
- Conversations stored so the owner can continue later.
- Vercel function duration must be configured high enough for multi-step tool loops (set `maxDuration`, stream output).

## 6. Constraints

- Free tiers: Supabase (500 MB DB, project pauses after ~1 week of inactivity — regular Health syncs should keep it active; builder to verify and note in README), Vercel Hobby (request body ~4.5 MB, function duration limits).
- Single user; personal health data → security in 5.2 is mandatory, not optional.
- Metric units everywhere; Europe/Brussels for display and week boundaries.

## 7. Testing & samples

- Small sample files in `samples/` so imports can be tested without real data: a short synthetic Zwift-like `.fit` (generated by a script in the repo), a Hevy CSV with a few workouts (including warmup sets, a superset, an extra unknown column, a reordered header), and Health Auto Export JSON with a run, a pool swim, and an indoor cycle that overlaps the sample Zwift ride.
- Backend tests (pytest) for: FIT parsing + NP/TSS, Hevy parsing + re-import idempotence, Health parsing + upsert, overlap dedupe in both arrival orders, auth/token rejection, read-only SQL role refusing writes, focus-engine calculations on fixtures.
- Frontend: type-check + build; light component tests where useful.

## 8. Delivery

- Git repo, committed in logical steps.
- Order: (1) repo skeleton, config, Supabase schema + RLS; (2) Zwift FIT import + sync script; (3) Hevy import; (4) Health ingest + overlap dedupe; (5) profile & measurements; (6) focus engine; (7) dashboard pages; (8) deploy to Vercel/Supabase + README (Supabase setup, Vercel env vars, iPhone Health Auto Export config step by step, launchd install); then v2 (9) coach.
- README must document exactly how to configure Health Auto Export on the iPhone (automation type REST API, URL `https://<app>.vercel.app/api/ingest/health`, header `Authorization: Bearer <token>`, data type Workouts (+ Body Mass metric), JSON format version, sync cadence and date range, route data off).

## 9. Left to the builder

- Exact zone cut-offs, effort-classification thresholds, target ranges for sets/muscle, plateau detection details.
- Seed content: exercise→muscle mapping for common Hevy exercise names, related-exercise ratio table.
- UI layout details, component structure, chart styling (keep it clean and consistent, light/dark).
- Caching strategy for focus facts.
- How the sample FIT file is generated.
