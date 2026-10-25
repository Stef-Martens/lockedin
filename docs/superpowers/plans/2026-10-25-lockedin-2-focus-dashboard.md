# LockedIn Plan 2 — Focus Engine & Dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opening LockedIn answers "am I improving?" and "what should I focus on next?". It shows an overview with totals and weekly volume, calculated focus suggestions (under-trained muscles with exercises and weights, a missing run/bike session type), recent wins, plateaus, a streak and a gentle comeback state, plus trend pages per sport.

**Architecture:** A new `lockedin/focus/` package of pure-ish functions. Each takes a SQLAlchemy `Connection` plus an explicit `now`, so tests control time. They read existing tables and return dataclasses. Three new tables hold the muscle taxonomy and an exercise library keyed by exercise **name** (Hevy's names). Owner exercises map to muscles through that library, and unmapped names can be tagged in the UI. Facts are computed on read (no cache yet). New FastAPI routes expose `/api/overview`, `/api/focus`, `/api/trends/{sport}`, `/api/gym/...`. The web app gets an Overview home, a Trends section (Bike/Run/Swim/Gym) and a reworked phone tab bar.

**Tech Stack:** As Plan 1 (FastAPI, SQLAlchemy Core, Postgres/Supabase, React + Vite + TS, Recharts 3).

**Spec:** `docs/superpowers/specs/2026-10-25-lockedin-design.md` (sections 5.5, 5.6). Plan 1: `docs/superpowers/plans/2026-10-25-lockedin-1-data-foundation.md`.

## Global Constraints

- All Plan 1 constraints still hold (owner-only auth on every route, RLS on every table, UTC storage, Brussels weeks Monday–Sunday, metric units, commit message suffix).
- **Counted session** = an activity with `superseded_by IS NULL` and `coalesce(sub_type,'') NOT LIKE 'walking%'`. Only counted sessions feed totals, streaks, comeback, mix, wins and trends.
- Every focus function takes `now: datetime` (aware UTC) and never calls `datetime.now()` itself. Routes pass `datetime.now(UTC)`.
- Tone (spec anti-goal "guilt UI"): no red for declines. A decline is always paired with what to do. After ≥7 days without a counted session, the overview leads with the comeback card instead of comparisons.
- Suggested weights for exercises the owner has never done are ×0.8 of the estimate and labelled "estimate, start light". With no basis for an estimate, show no weight.
- Charts: load the `dataviz` skill before chart code. Sport colours come from the validated tokens (`--sport-*`). Use one axis per chart; a stacked chart gets a legend, a hover tooltip and a table view.
- Plan 1 deferred minor folded in here because this plan adds tables: the migration must `alter default privileges ... revoke` from `anon, authenticated`.

## Review Focus

1. **No data / very little data.** A brand-new account (no rides, no gym) must render every page and endpoint without errors. Focus shows "not enough data yet", never a crash or `NaN`. → tests in Tasks 3–6.
2. **Owner's exercise names exactly as Hevy writes them** (e.g. `Seated Cable Row - V Grip (Cable)`, `Cable Twist (Up to down)`). All 23 of the owner's current exercises must be mapped by the seed, so coverage isn't empty on day one. → test in Task 1.
3. **Dumbbell weights.** Hevy logs dumbbell exercises per dumbbell. A suggestion for a dumbbell exercise is a per-dumbbell weight and is labelled "per dumbbell". → test in Task 3.
4. **Week boundaries in Brussels.** A Sunday 23:30 Brussels session counts in that week's totals and streak, not the next. → test in Task 4.
5. **Superseded and walk rows.** Watch duplicates and walks never inflate totals, streaks, wins or the weekly chart. → test in Task 4.

---

## File Structure

```
supabase/migrations/20261026000001_focus.sql   muscles, library_exercises, library_muscles + seed, default privileges
lockedin/focus/__init__.py
lockedin/focus/sessions.py      counted_sessions(), load helpers shared by all focus modules
lockedin/focus/zones.py         max_hr_at(), hr_zone(), power_zone(), zone bounds
lockedin/focus/effort.py        classify_effort(), effort_for_window()
lockedin/focus/coverage.py      muscle_coverage(), unmapped_exercises()
lockedin/focus/suggest.py       gym_suggestions(), suggested_load()
lockedin/focus/mix.py           effort_mix(), session_suggestions()
lockedin/focus/consistency.py   week_streak(), comeback(), totals(), weekly_volume()
lockedin/focus/trends.py        bike_trends(), run_trends(), swim_trends(), gym_exercise_progress(), gym_weekly_volume()
lockedin/focus/wins.py          recent_wins(), plateaus()
lockedin/focus/facts.py         focus_facts() — assembles everything (also Plan 3's coach tool)
lockedin/routes/overview.py     GET /api/overview, GET /api/focus
lockedin/routes/trends.py       GET /api/trends/{sport}, /api/gym/exercises, /api/gym/exercises/{id}, PUT .../muscles, GET /api/muscles
tests/focus_helpers.py          add_session(), add_gym() fixture builders
tests/test_focus_*.py
web/src/pages/Overview.tsx
web/src/pages/Trends.tsx        sport switcher → BikeTrends / RunTrends / SwimTrends / GymTrends
web/src/components/WeeklyVolumeChart.tsx, FocusCard.tsx, MuscleCoverage.tsx, WinsStrip.tsx
```

---

### Task 1: Muscle taxonomy, exercise library and seed

**Files:**
- Create: `supabase/migrations/20261026000001_focus.sql`
- Test: `tests/test_focus_library.py`; extend `tests/test_schema.py` `TABLES`

**Interfaces:**
- Produces tables:
  - `muscles (key text pk, name text, region text, target_low real, target_high real, sort smallint)`
  - `library_exercises (name text pk, equipment text check in ('barbell','dumbbell','cable','machine','bodyweight','other'), related_to text null references library_exercises(name), ratio real null, created_by text default 'seed')`
  - `library_muscles (exercise_name text references library_exercises(name) on delete cascade, muscle_key text references muscles(key), role text check in ('primary','secondary'), primary key (exercise_name, muscle_key))`
  - RLS on all three, `revoke all ... from anon, authenticated`, and `alter default privileges in schema public revoke all on tables from anon, authenticated` (plus sequences and functions).
- Muscles (key · name · region · weekly set target low–high):
  `upper_chest` Upper chest · chest · 4–10; `mid_lower_chest` Mid/lower chest · chest · 6–12; `front_delt` Front delts · shoulders · 4–10; `side_delt` Side delts · shoulders · 8–16; `rear_delt` Rear delts · shoulders · 6–12; `triceps` Triceps · arms · 8–14; `biceps` Biceps · arms · 8–14; `forearms` Forearms · arms · 0–8; `lats` Lats · back · 8–14; `mid_back` Mid back · back · 8–14; `upper_back_traps` Traps · back · 4–10; `lower_back` Lower back · back · 3–8; `abs` Abs · core · 6–12; `obliques` Obliques · core · 3–8; `glutes` Glutes · legs · 6–12; `quads` Quads · legs · 8–14; `hamstrings` Hamstrings · legs · 6–12; `adductors` Adductors · legs · 3–8; `abductors` Abductors · legs · 0–6; `calves` Calves · legs · 6–12. A target_low of 0 means it is never flagged "low".
- Seed **all 23 owner exercises**, using exactly these names and mappings (P = primary, S = secondary):

  | Exercise | equipment | P | S |
  |---|---|---|---|
  | Overhead Press (Dumbbell) | dumbbell | front_delt | side_delt, triceps, upper_chest |
  | Lateral Raise (Dumbbell) | dumbbell | side_delt | |
  | Lateral Raise (Cable) | cable | side_delt | |
  | Incline Bench Press (Dumbbell) | dumbbell | upper_chest | front_delt, triceps |
  | Bench Press (Barbell) | barbell | mid_lower_chest | upper_chest, front_delt, triceps |
  | Chest Fly (Machine) | machine | mid_lower_chest | upper_chest, front_delt |
  | Triceps Dip | bodyweight | triceps | mid_lower_chest, front_delt |
  | Triceps Extension (Cable) | cable | triceps | |
  | Triceps Pushdown | cable | triceps | |
  | Hammer Curl (Cable) | cable | biceps | forearms |
  | Bicep Curl (Cable) | cable | biceps | forearms |
  | Preacher Curl (Machine) | machine | biceps | |
  | Pull Up | bodyweight | lats | biceps, mid_back |
  | Lat Pulldown (Cable) | cable | lats | biceps, mid_back |
  | Seated Cable Row - V Grip (Cable) | cable | mid_back, lats | biceps, rear_delt |
  | Chest Supported Incline Row (Dumbbell) | dumbbell | mid_back | lats, rear_delt, biceps |
  | Chest Supported Reverse Fly (Dumbbell) | dumbbell | rear_delt | mid_back |
  | Leg Press Horizontal (Machine) | machine | quads, glutes | hamstrings, adductors |
  | Leg Extension (Machine) | machine | quads | |
  | Seated Leg Curl (Machine) | machine | hamstrings | |
  | Cable Crunch | cable | abs | |
  | Cable Twist (Up to down) | cable | obliques | abs |
  | Side Bend (Cable) | cable | obliques | |

- Seed **suggestion-only exercises** (so every muscle has at least one primary option), with `related_to`/`ratio` where an estimate is reasonable:

  | Exercise | equip | P | S | related_to × ratio |
  |---|---|---|---|---|
  | Standing Calf Raise (Machine) | machine | calves | | Leg Press Horizontal (Machine) × 0.5 |
  | Seated Calf Raise | machine | calves | | Leg Press Horizontal (Machine) × 0.3 |
  | Hip Thrust (Barbell) | barbell | glutes | hamstrings | Leg Press Horizontal (Machine) × 0.6 |
  | Romanian Deadlift (Barbell) | barbell | hamstrings, glutes | lower_back | Leg Press Horizontal (Machine) × 0.4 |
  | Bulgarian Split Squat | bodyweight | quads, glutes | adductors | — |
  | Hip Adduction (Machine) | machine | adductors | | — |
  | Hip Abduction (Machine) | machine | abductors | glutes | — |
  | Back Extension (Hyperextension) | bodyweight | lower_back | glutes, hamstrings | — |
  | Shrug (Dumbbell) | dumbbell | upper_back_traps | | Overhead Press (Dumbbell) × 1.2 |
  | Face Pull | cable | rear_delt | upper_back_traps, mid_back | Seated Cable Row - V Grip (Cable) × 0.35 |
  | Rear Delt Reverse Fly (Machine) | machine | rear_delt | mid_back | Chest Supported Reverse Fly (Dumbbell) × 2.0 |
  | Overhead Triceps Extension (Cable) | cable | triceps | | Triceps Extension (Cable) × 0.9 |
  | Skullcrusher (Barbell) | barbell | triceps | | Triceps Extension (Cable) × 0.8 |
  | Incline Curl (Dumbbell) | dumbbell | biceps | | — |
  | Wrist Curl (Barbell) | barbell | forearms | | — |
  | Hanging Leg Raise | bodyweight | abs | | — |
  | Low Cable Fly Crossover | cable | upper_chest | front_delt | Chest Fly (Machine) × 0.5 |
  | Cable Fly Crossover | cable | mid_lower_chest | | Chest Fly (Machine) × 0.5 |
  | Front Raise (Dumbbell) | dumbbell | front_delt | | Lateral Raise (Dumbbell) × 1.0 |

- [ ] **Step 1: Write failing tests**

```python
OWNER = ["Overhead Press (Dumbbell)", "Lateral Raise (Dumbbell)", "Incline Bench Press (Dumbbell)", "Hammer Curl (Cable)",
         "Bicep Curl (Cable)", "Preacher Curl (Machine)", "Bench Press (Barbell)", "Seated Cable Row - V Grip (Cable)",
         "Pull Up", "Triceps Extension (Cable)", "Chest Supported Reverse Fly (Dumbbell)", "Chest Fly (Machine)",
         "Leg Press Horizontal (Machine)", "Leg Extension (Machine)", "Seated Leg Curl (Machine)", "Cable Crunch",
         "Cable Twist (Up to down)", "Triceps Dip", "Lat Pulldown (Cable)", "Lateral Raise (Cable)", "Triceps Pushdown",
         "Chest Supported Incline Row (Dumbbell)", "Side Bend (Cable)"]
def test_every_owner_exercise_has_a_primary_muscle(conn): ...   # each name has ≥1 primary row
def test_every_flaggable_muscle_has_a_primary_exercise(conn): ...  # muscles with target_low > 0 have ≥1 primary
def test_twenty_muscles_with_targets(conn): ...  # count 20; side_delt (8,16); forearms target_low 0
def test_related_ratios_point_at_library_names(conn): ...  # FK holds; Shrug → Overhead Press × 1.2
```
  Extend `TABLES` in `test_schema.py` with the 3 tables. Also add a test that `pg_default_acl` has no grants to `anon`/`authenticated` in schema public.
- [ ] **Step 2: Run** → FAIL.  **Step 3: Write the migration.**  **Step 4: Run** `make test` → PASS.
- [ ] **Step 5: Commit** `feat: muscle taxonomy and exercise library seed`.

---

### Task 2: Counted sessions, zones and effort classification

**Files:**
- Create: `lockedin/focus/__init__.py`, `sessions.py`, `zones.py`, `effort.py`, `tests/focus_helpers.py`
- Test: `tests/test_focus_effort.py`

**Interfaces:**
- `tests/focus_helpers.py`:
  - `add_session(conn, sport, start: datetime, duration_s: int, *, source='healthfit', sub_type=None, distance_m=None, avg_hr=None, max_hr=None, np=None, avg_power=None, best_20m_power=None, swim_pace=None, avg_pace=None, power=None, hr=None, superseded_by=None) -> int` inserts an activity and, if `power`/`hr` lists are given, a 1 Hz stream.
  - `add_gym(conn, start: datetime, sets: list[tuple[str, float | None, int, str]], title='Gym', duration_s=3600) -> int` takes `(exercise, weight_kg, reps, set_type)`, upserts exercises, computes `e1rm` with the Plan 1 `e1rm()` rule, and sets `source='hevy', sport='gym'`.
- `sessions.py`:
  - `COUNTED_SQL` (where-clause fragment).
  - `@dataclass Session(id, sport, sub_type, source, start_at, duration_s, distance_m, avg_hr, max_hr, np, avg_power, best_20m_power, avg_pace_s_per_km, swim_pace_s_per_100m)`.
  - `counted_sessions(conn, since: datetime, until: datetime, sport: str | None = None) -> list[Session]`, oldest first.
- `zones.py`:
  - `max_hr_at(conn, now) -> int | None`: `profile.max_hr_override`. Otherwise the highest counted `max_hr` in the last 365 days, if it lies in 140–215. Otherwise `220 − age` when date_of_birth is set. Otherwise None.
  - `hr_zone(hr: int, max_hr: int) -> int`, 1–5 by % of max: <60 → 1, 60–70 → 2, 70–80 → 3, 80–90 → 4, ≥90 → 5 (lower bound inclusive).
  - `power_zone(watts: float, ftp: float) -> int`, Coggan-style 1–5 by % of FTP: <56 → 1, 56–75 → 2, 76–90 → 3, 91–105 → 4, >105 → 5.
  - `hr_zone_bounds(max_hr) -> dict[int, tuple[int, int]]`, used in suggestion copy.
- `effort.py`:
  - `Effort = Literal["easy", "steady", "hard", "long"]`.
  - `classify_effort(s: Session, *, power: list | None, hr: list | None, ftp: float | None, max_hr: int | None, median_duration_s: float | None, median_swim_pace: float | None) -> Effort | None`.

  ```
  zones = power zones if (bike and power and ftp) else hr zones if (hr and max_hr) else None
  if zones (per-sample, ignoring None/0):
      easy_frac = share in z1–2 ; hard_frac = share in z4–5
      base = "hard" if hard_frac >= 0.15 else "easy" if easy_frac >= 0.75 else "steady"
  elif bike and np and ftp:   IF = np/ftp → <0.75 easy, ≤0.88 steady, else hard
  elif avg_hr and max_hr:     pct = avg_hr/max_hr → <0.75 easy, ≤0.85 steady, else hard
  elif swim and swim_pace and median_swim_pace: ≥5% faster → hard, ≥5% slower → easy, else steady
  else: return None
  long if base != "hard" and median_duration_s and duration_s >= 1.5 × median_duration_s and (no zones or easy_frac >= 0.6)
  ```
  - `effort_for_window(conn, now, days=28, sport=None) -> list[tuple[Session, Effort | None]]` loads streams and the medians: same sport, counted, last 56 days, medians need ≥3 sessions. Uses `ftp_at` from Plan 1.

- [ ] **Step 1: Write failing tests** with literal expectations:
  - `hr_zone(130, 190) == 2`; `hr_zone(171, 190) == 5`.
  - `power_zone(200, 250) == 3`; `power_zone(270, 250) == 5`.
  - `max_hr_at`: an override wins. Without one, the observed 188 is used. An observed 250 is implausible → falls back to 220 − age (DOB 1995-04-12, now 2026-10-26 → 189). Nothing → None.
  - `classify_effort`:
    - 60 min at 140 W with FTP 250 → easy.
    - 60 min alternating 4 min @ 280 W / 4 min @ 150 W → hard.
    - 60 min @ 210 W → steady.
    - HR-only run at a steady 68% of max with duration 2× median → long.
    - A run with only `avg_hr`, at 88% → hard.
    - A swim 6% faster than median → hard.
    - No data at all → None.
  - `counted_sessions` excludes walks and superseded rows.
- [ ] **Step 2: Run** → FAIL.  **Step 3: Implement.**  **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: counted sessions, HR/power zones and effort classification`.

---

### Task 3: Muscle coverage and gym suggestions

**Files:**
- Create: `lockedin/focus/coverage.py`, `lockedin/focus/suggest.py`
- Test: `tests/test_focus_gym.py`

**Interfaces:**
- `@dataclass MuscleCoverage(key, name, region, sets_per_week: float, target_low: float, target_high: float, status: Literal["low","ok","high"])`
- `muscle_coverage(conn, now, days=28) -> list[MuscleCoverage]`:
  - Takes non-warmup sets from counted gym sessions in `(now − days, now]`.
  - Each set credits its exercise's primary muscles 1.0 and its secondary muscles 0.5.
  - `sets_per_week = credit / (days / 7)`.
  - Status: `low` if `< target_low`, `high` if `> target_high × 1.5`, else `ok`.
  - Ordered by `muscles.sort`.
  - Returns `[]` when there's no gym session in the window.
- `unmapped_exercises(conn, now, days=90) -> list[str]` lists exercise names done in the window that have no library entry.
- `@dataclass GymSuggestion(muscle_key, muscle_name, exercise, sets: int, reps: str, weight_kg: float | None, per_dumbbell: bool, estimate: bool, reason: str)`
- `suggested_load(e1rm: float, reps: int = 12) -> float` is the Epley inverse `e1rm / (1 + reps/30)`, rounded **down** to 2.5 kg at ≥ 20 kg and to 1 kg below that. (12 reps at full effort ≈ 10 reps at RPE 8, so the suggestion reads "3 × 8–12".)
- `gym_suggestions(conn, now, limit=3) -> list[GymSuggestion]`. This produces **add-on suggestions** (spec 5.5), not full sessions.
  - Pick the `low` muscles, sorted by `(target_low − sets_per_week) / target_low` descending, ties broken by `muscles.sort`, and take up to `limit`. If coverage is empty (no gym data), return `[]`.
  - For each muscle, choose an exercise in this order:
    - **(a)** an owner exercise from the last 90 days that has the muscle as primary, most recently done first. Weight = `suggested_load(best e1RM in the last 56 days)`, `estimate=False`.
    - **(b)** a library exercise whose `related_to` the owner has e1RM history for. Weight = `suggested_load(related_e1rm × ratio) × 0.8`, rounded down again, `estimate=True`.
    - **(c)** any library exercise with that primary. Weight `None`, `estimate=True`.
  - Bodyweight exercises: `weight_kg=None`. Reps are "8–12", or `round(best_reps × 0.8)`–`best_reps` if there's history.
  - `per_dumbbell = equipment == 'dumbbell'`.
  - `reason` is e.g. `"Calves: 0 sets/week, aim for 6–12"`.

- [ ] **Step 1: Write failing tests** (fixtures through `add_gym`, `now = 2026-10-26T12:00Z`):
  - **Coverage:**
    - 4 weeks × (Bench Press (Barbell) 3 normal sets + 1 warmup) → mid_lower_chest = 3.0/week, upper_chest = triceps = front_delt = 1.5/week.
    - A warmup doesn't count.
    - A walk-only account → `[]`.
  - **`unmapped_exercises`:** includes `"Zercher Squat"` after one set of it.
  - **`suggested_load`:** `suggested_load(100) == 70.0` (100/1.4 = 71.4 → 70.0); `suggested_load(26) == 18.0` (18.57 → 18).
  - **Suggestions:**
    - Owner with Leg Press e1RM 200 (1 session within the window) and no calf work → `gym_suggestions(limit=20)` contains, for `calves`, `Standing Calf Raise (Machine)`, weight `suggested_load(100) × 0.8` → 70 × 0.8 = 56 → rounded down 55.0, `estimate=True`.
    - Owner who did Triceps Extension (Cable) 6 weeks ago (e1RM 40) but nothing in the last 4 weeks → the `triceps` item in `gym_suggestions(limit=20)` uses Triceps Extension (Cable), `estimate=False`, weight 27.5.
    - Ordering: with chest done (3 sets/week, target 6) and calves not done at all, calves (deficit 1.0) comes before mid/lower chest (deficit 0.5).
    - Overhead Press (Dumbbell) history → `per_dumbbell=True`.
    - Empty DB → `[]`.
- [ ] **Step 2: Run** → FAIL.  **Step 3: Implement.**  **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: muscle coverage and add-on gym suggestions with weights`.

---

### Task 4: Totals, weekly volume, streak, comeback, effort mix and session suggestions

**Files:**
- Create: `lockedin/focus/consistency.py`, `lockedin/focus/mix.py`
- Test: `tests/test_focus_consistency.py`, `tests/test_focus_mix.py`

**Interfaces:**
- `consistency.py`:
  - `@dataclass SportTotals(time_s: int, distance_m: float, sessions: int)`
  - `totals(conn, now) -> dict[Literal["week","month"], dict[str, SportTotals]]` covers the Brussels current week (from Monday) and calendar month. Keys are `bike, run, swim, gym, other`, all present (zeros).
  - `weekly_volume(conn, now, weeks: int) -> list[dict]` returns one row per Brussels week, oldest first and including the current week: `{"week_start": date, "bike": minutes, "run": ..., "swim": ..., "gym": ..., "other": ...}`.
  - `week_streak(conn, now) -> int` counts consecutive weeks with ≥2 counted sessions, ending last week. The current week adds 1 if it already has ≥2.
  - `@dataclass Comeback(days_since: int, last_session: Session | None, suggestion: str)`
  - `comeback(conn, now) -> Comeback | None`: present when there are ≥7 days since the last counted session, or no sessions ever. Suggestion text:
    - bike was the most frequent sport in the last 90 days → `"Ease back in: a 30-minute easy ride, just spinning."`
    - otherwise gym → `"Ease back in: a short full-body session, 3 exercises × 3 sets, nothing heavy."`
    - otherwise → `"Ease back in: 30 minutes of something easy you enjoy."`
- `mix.py`:
  - `@dataclass EffortMix(sport, counts: dict[Effort, int], unclassified: int)`
  - `effort_mix(conn, now, sport, days=28) -> EffortMix`
  - `@dataclass SessionSuggestion(sport, kind: Effort, title: str, detail: str, reason: str)`
  - `session_suggestions(conn, now) -> list[SessionSuggestion]`. These rules apply per sport, run and bike only, and only when the sport has ≥2 counted sessions in the last 42 days:
    - **No long session in the last 21 days** →
      - run: `"Long easy run"`, `"60–75 min in zone 2 (HR {z2_lo}–{z2_hi} bpm)"`
      - bike: `"Long easy ride"`, `"90 min in zone 2 ({p_lo}–{p_hi} W)"`
    - **≥3 sessions in the last 21 days and none hard** →
      - run: `"Intervals"`, `"6 × 3 min hard (zone 4, HR {z4_lo}–{z4_hi}) with 2 min easy jogs"`
      - bike: `"Intervals"`, `"4 × 8 min at 91–105% FTP ({w_lo}–{w_hi} W), 4 min easy between"`
    - **Hard sessions > 50% of the classified sessions in the last 28 days** → an easy session of 45 min in zone 2.

    Zone numbers come from `hr_zone_bounds`/FTP. When they're unknown, omit the bracket. At most 2 suggestions, ordered run before bike.

- [ ] **Step 1: Write failing tests** (`now = 2026-10-26T09:00Z`, a Monday):
  - **Totals:**
    - A ride Sun 2026-10-25 22:30Z (= 23:30 Brussels) is **last** week.
    - A ride Mon 2026-10-26 06:00Z is this week.
    - A superseded Watch ride and a walk are excluded from totals and `weekly_volume`.
  - **`weekly_volume`:** with `weeks=3` → 3 rows, week_starts 2026-10-12, 10-19, 10-26.
  - **`week_streak`:** with 2 sessions in each of the last 3 weeks and 0 this week → 3; add 2 this week → 4; one week with a single session breaks it.
  - **`comeback`:**
    - Last session 9 days ago → `days_since == 9`, with the bike text when bike dominates.
    - 3 days ago → None.
    - Empty DB → `days_since` large and `last_session is None`.
  - **`session_suggestions`:**
    - 4 steady runs (HR 78%) in 21 days, none long → includes the run "Intervals" and the "Long easy run" titles, at most 2.
    - Only 1 run in 42 days → no run suggestion.
    - Max HR 190 → zone 2 is 114–133 bpm, and that text appears.
- [ ] **Step 2–4:** RED → implement → GREEN.
- [ ] **Step 5: Commit** `feat: totals, weekly volume, streak, comeback and run/bike session suggestions`.

---

### Task 5: Trends, wins and plateaus

**Files:**
- Create: `lockedin/focus/trends.py`, `lockedin/focus/wins.py`
- Test: `tests/test_focus_trends.py`, `tests/test_focus_wins.py`

**Interfaces:**
- `trends.py`. All functions take `(conn, now, weeks=26)` and return JSON-ready dicts, using counted sessions only.
  - `bike_trends`: `{"rides": [{"date", "np", "avg_power", "avg_hr", "efficiency": np/avg_hr | None, "best_20m"}], "weekly": [{"week_start", "minutes", "tss"}], "ftp": float | None, "mix": EffortMix}`
  - `run_trends`: `{"runs": [{"date", "pace_s_per_km", "avg_hr", "aerobic_efficiency": (1000/pace)*60/avg_hr | None, "distance_m"}], "weekly": [{"week_start", "km"}], "mix": EffortMix}`. Aerobic efficiency is metres per minute per bpm (higher = better).
  - `swim_trends`: `{"swims": [{"date", "distance_m", "pace_s_per_100m"}], "weekly": [{"week_start", "m"}]}`
  - `gym_exercise_progress(conn, exercise_id) -> {"exercise", "sessions": [{"date", "best_e1rm", "best_set": {"weight_kg", "reps"}}]}` covers all time, oldest first.
  - `gym_weekly_volume(conn, now, weeks)`: `[{"week_start", "volume_kg": Σ weight×reps (non-warmup, weight not null)}]`
- `wins.py`:
  - `@dataclass Win(kind: str, title: str, detail: str, date: date, activity_id: int | None)`
  - `recent_wins(conn, now, days=14) -> list[Win]`, newest first, at most 6. Each kind compares against everything **before** that session:
    - `e1rm_pr`: an exercise's best e1RM in the window beats every earlier e1RM → `"New best: Bench Press (Barbell)"`, `"est. 1RM 96.0 kg (was 92.5)"`.
    - `power_pr`: `best_20m_power` beats every earlier one → `"Best 20-min power"`, `"248 W (was 241)"`.
    - `longest`: a ride or run distance beats all earlier ones for that sport.
    - `fastest_run`: pace for runs ≥3 km beats all earlier runs ≥3 km.
    - `swim_pace`: pace for swims ≥400 m beats all earlier ones.
    - `consistency`: counted sessions in the last 28 days > the same 28 days a year ago (only if that period has ≥1 session) → `"More consistent than last year"`.

    A win needs prior history, so the very first session of a kind is never a "PR".
  - `@dataclass Plateau(kind, title, detail, suggestion)`
  - `plateaus(conn, now) -> list[Plateau]`:
    - **Gym:** an exercise done in ≥4 sessions in the last 42 days whose best e1RM in that window is ≤ its best in the 42 days before (which must also have ≥2 sessions) → suggestion `"Change the stimulus for 3–4 weeks: try 4 × 6–8 a bit heavier, or swap to a variation."`
    - **Bike:** ≥4 rides in the last 56 days and the best 20-min power in that window ≤ the best in the 56 days before (≥2 rides) → `"Add one interval ride a week (4 × 8 min at threshold) for a month."`

- [ ] **Step 1: Write failing tests:**
  - `run_trends` aerobic efficiency for pace 300 s/km at HR 150 = 200/150 ≈ 1.333.
  - `bike_trends` efficiency = np/avg_hr.
  - `gym_weekly_volume` excludes warmups.
  - `gym_exercise_progress` best set per session.
  - Wins: a bench e1RM 96 after a prior 92.5 → one `e1rm_pr` with detail `"est. 1RM 96.0 kg (was 92.5)"`. First-ever session → no wins. A Watch duplicate never yields a win.
  - Plateaus: a gym plateau when e1RM is flat; none when it improves; none with too few sessions.
- [ ] **Step 2–4:** RED → implement → GREEN.
- [ ] **Step 5: Commit** `feat: per-sport trends, recent wins and plateau detection`.

---

### Task 6: Focus facts and API routes

**Files:**
- Create: `lockedin/focus/facts.py`, `lockedin/routes/overview.py`, `lockedin/routes/trends.py`
- Modify: `lockedin/app.py`
- Test: `tests/test_routes_overview.py`, `tests/test_routes_trends.py`

**Interfaces:**
- `focus_facts(conn, now) -> dict` (JSON-ready; Plan 3's coach tool returns this verbatim):
  `{"generated_at", "zones": {"max_hr", "ftp", "hr_zones", "power_zones"}, "coverage": [...], "unmapped": [...], "gym_suggestions": [...], "session_suggestions": [...], "mix": {"run": ..., "bike": ...}, "plateaus": [...], "wins": [...], "streak", "comeback"}`
- `GET /api/overview?weeks=12` (12 or 26, else 422) returns:
  - `{"totals", "weekly", "streak", "comeback", "wins", "focus": [up to 3 items], "measure_due": bool, "last_tape_measurement_on"}`
  - `focus` interleaves: `gym_suggestions[0]`, `session_suggestions[0]`, `gym_suggestions[1]`, ... Each item has `{"type": "gym" | "session", ...fields}`.
  - `measure_due` = no tape measurement, or the last one more than 28 days ago.
- `GET /api/focus` → `focus_facts`.
- `GET /api/trends/{sport}` for `bike|run|swim` (others 404). Query `weeks` defaults to 26.
- `GET /api/gym/exercises` → `[{"id", "name", "sessions", "last_done", "best_e1rm", "mapped": bool, "muscles": [{"key", "role"}]}]`, ordered by most recently done.
- `GET /api/gym/exercises/{id}` → `gym_exercise_progress`.
- `GET /api/gym/volume?weeks=26` → `gym_weekly_volume`.
- `GET /api/gym/coverage` → `{"coverage", "unmapped"}`.
- `GET /api/muscles` → the taxonomy.
- `PUT /api/gym/exercises/{id}/muscles` with body `{"equipment", "primary": [keys ≥1], "secondary": [keys]}`. This upserts a `library_exercises` row (`created_by='owner'`) for that exercise name and replaces its `library_muscles`. Unknown muscle key → 422.
- All routes are owner-only.

- [ ] **Step 1: Write failing tests:**
  - Overview on an empty DB → 200 with zero totals, comeback present, `focus == []`, `measure_due` true.
  - Overview with the Plan 1 sample imports → bike totals non-zero in the right week.
  - `weeks=7` → 422.
  - `/api/focus` keys present.
  - Trends for each sport → 200. `/api/trends/gym` → 404.
  - Tagging an unmapped exercise makes it disappear from `unmapped` and adds coverage. A bad muscle key → 422.
  - Everything is 401 without a token.
- [ ] **Step 2–4:** RED → implement → GREEN.
- [ ] **Step 5: Commit** `feat: overview, focus, trends and gym API`.

---

### Task 7: Navigation and the Overview page

**Files:**
- Create: `web/src/pages/Overview.tsx`, `web/src/components/{WeeklyVolumeChart,FocusCard,WinsStrip}.tsx`, `web/src/lib/focus.ts` (types + copy helpers)
- Modify: `web/src/App.tsx` (index → Overview; add `/trends/:sport`), `web/src/components/Layout.tsx`, `web/src/styles.css`
- Test: `web/src/lib/focus.test.ts`

**Interfaces:**
- **Navigation:**
  - Desktop topnav: Overview · Activities · Trends · Body · Import.
  - Phone tab bar: the same 5 entries (labels Home, Activities, Trends, Body, Import) in a 5-column grid.
- **`focus.ts`:**
  - `focusLine(item): {title: string, detail: string}`. For a gym item: title `"{exercise}"`, detail `"3 × 8–12 at 55 kg per dumbbell · estimate, start light"`. Drop parts that don't apply: no weight → `"3 × 8–12, start light"`; bodyweight → `"3 × 8–12"`.
  - `pct(n)` and `formatMinutes(m)` (`"1 h 05"` / `"45 min"`).
- **Overview layout, top to bottom:**
  1. **Comeback card** (when present). Title `"Welcome back"`, body `"Last session {n} days ago. {suggestion}"`. No comparisons render above it.
  2. **"Focus this week" card:** up to 3 lines from `focusLine`, each with the reason in muted text. Empty → `"Keep logging for a couple of weeks and suggestions will show up here."`
  3. **Wins strip:** horizontally scrollable chips. Hidden when empty.
  4. **Totals:** this week / this month toggle. One tile per sport with sessions > 0 (time, distance where relevant, sessions). Streak tile `"{n}-week streak"` when ≥2.
  5. **Weekly volume chart:** stacked bars by sport (minutes), 12/26 toggle, a legend, a hover tooltip with per-sport minutes, and a "Show table" toggle.
  6. **"Time to measure" note** when `measure_due`, linking to /body.
- **`WeeklyVolumeChart`:**
  - Recharts `BarChart` with stacks in fixed order bike, run, swim, gym, other. Colours via `useCssVar('--sport-*')`.
  - Bars ≤24 px, with a 2 px surface-coloured gap between stacked segments (`stroke` = surface colour, width 2).
  - Top segment radius 4. One y-axis in minutes. Tick labels `d MMM`.
- [ ] **Step 1:** load the `dataviz` skill, then write the failing test for `focusLine` with literal strings for: a weighted gym item, an estimate, per-dumbbell, bodyweight, and a session item → `{title: "Long easy run", detail: "60–75 min in zone 2 (HR 114–133 bpm)"}`.
- [ ] **Step 2–4:** RED → implement → GREEN (`npm --prefix web test -- --run`, `npm --prefix web run build`).
- [ ] **Step 5: Commit** `feat(web): overview with focus, wins, totals, streak and weekly volume`.

---

### Task 8: Trends pages (Bike, Run, Swim, Gym) and exercise tagging

**Files:**
- Create: `web/src/pages/Trends.tsx`, `web/src/components/MuscleCoverage.tsx`
- Modify: `web/src/pages/ActivityDetail.tsx` (run cadence: show `avg_cadence × 2` as "spm"; Plan 1 deferred minor), `web/src/lib/types.ts`

**Interfaces:**
- `/trends/:sport`, with a segmented control Bike · Run · Swim · Gym (default bike).
  - **Bike:**
    - Chart: NP per ride (power colour)
    - Chart: efficiency NP/HR per ride
    - Chart: best 20-min power
    - Tile: current FTP estimate
    - Effort mix: four labelled counts with text labels, not colour-only
    - The session suggestion for bike, if any
  - **Run:**
    - Chart: pace per run (reversed axis)
    - Chart: aerobic efficiency
    - Chart: weekly km (bars, run colour)
    - Effort mix
    - Session suggestion
  - **Swim:** weekly metres (bars) and pace per 100 m per swim (reversed).
  - **Gym:**
    - **Muscle coverage:** grouped by region. Each muscle row shows the name, a horizontal bar of sets/week with the target range drawn as a band, and a text status ("low" / "ok" / "a lot"). Low rows show the matching add-on suggestion inline.
    - **Weekly volume** (kg×reps) bars.
    - **Exercise list:** each exercise links to an inline progress chart (best e1RM per session).
    - **"Tag your exercises"** section for unmapped names: equipment select, primary/secondary muscle multi-selects, Save. Calls PUT and refreshes coverage.
- Empty states on every tab: `"No rides yet"` etc., with a link to /import.

- [ ] **Step 1: Implement** pages and components (logic is covered by API tests; UI is verified in Step 2).
- [ ] **Step 2: Verify in the browser.** Load the owner's real data into the **local** stack:
  - Run `supabase start` and `supabase db reset`, then `make owner`.
  - Upload `~/Documents/Zwift/Activities/*.fit` and `~/Downloads/workouts.csv` through the Import page.
  - Then drive with Playwright at 1200 px light and 375 px dark: Overview renders focus/wins/totals/chart; each Trends tab renders; the gym coverage shows the owner's real gaps (expect calves, glutes, lower back, traps low); tagging a made-up exercise works.
  - Pass criteria: no console errors and no horizontal overflow.
- [ ] **Step 3: Commit** `feat(web): trends pages, muscle coverage and exercise tagging`.

---

### Task 9: Deploy notes

- [ ] Add the README section "Dashboard & focus" (what each suggestion means and how weights are estimated), plus the deploy order: run `supabase db push` (new migration) **before** `git push`.
- [ ] Run `make test`, `npm --prefix web test -- --run` and `npm --prefix web run build`, and confirm all green.
- [ ] Commit `docs: dashboard and focus engine`.
