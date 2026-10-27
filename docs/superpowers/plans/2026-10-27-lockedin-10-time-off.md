# Time Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner record vacations and an operation (per-activity restrictions, each with its own end), and make planning, the coach, focus tips, the streak and the forecasts respect them.

**Architecture:** One table `time_off` and one module `lockedin/timeoff.py` answer "what's off on day D" (`off_on`, `away_on`, `off_muscles`). Every consumer asks that module. Gym restrictions reach the planner, focus tips and Muscles page by being merged into `load_preferences(conn, on=day)` as extra muscles to leave out. The rest (agenda, coach, streak, forecast, Overview) call the helpers directly. The web app adds a Time off card on the Agenda page and shows the windows wherever days are drawn.

**Tech Stack:** FastAPI + SQLAlchemy `text()` on Postgres (Supabase), pytest against local Postgres; React 18 + TypeScript + Vite + vitest; recharts.

**Spec:** `docs/superpowers/specs/2026-10-27-lockedin-time-off-design.md`

## Global Constraints

- All days are Brussels days (`lockedin.timeutil.TZ`); `until` is inclusive (the last day it's off).
- Categories, exactly: `run`, `bike`, `swim`, `upper`, `core`, `lower`, `all`. Regions: `upper` = muscle regions `arms`, `back`, `chest`, `shoulders`; `core` = `core`; `lower` = `legs`. `all` covers every category.
- Reasons, exactly: `vacation`, `injury` (shown "Vacation" / "Operation or injury").
- Nothing is ever deleted or moved because of time off; clashing items are flagged.
- The coach gives no medical advice and saves time off only after the owner agrees.
- Migration `supabase/migrations/20261028000005_time_off.sql` is applied to production (`supabase db push`) before the code reaches `main`.
- Work on `main` in the main checkout; no worktrees. Run Python tests with `.venv/bin/python -m pytest`, web checks from `web/`: `npx tsc -b`, `npx vitest run`, `npm run lint`, `npm run build`; `.venv/bin/ruff check .`.
- Copy follows the app's plain, short style ("Running is off until 17 Dec").

## Review Focus

1. Overlapping entries (a vacation inside the operation's window): the union applies; the band names both; nothing double-counts.
2. An entry whose `until` is before its `start`, or a restriction list that's empty: refused with a plain 422 message.
3. The first day back (`until + 1`): the activity is allowed again and plannable; the "easy for 2 weeks" note starts that day.
4. A gym routine that's half upper body during `upper` off: only the upper-body exercises are skipped; if every exercise is restricted, the planner says so instead of returning an empty plan.
5. Editing or deleting an entry rebuilds today's saved plan (the preferences fingerprint changes) and re-shows Zwift workouts the Mac didn't get.

---

### Task 1: The time-off model, store and API

**Files:**
- Create: `supabase/migrations/20261028000005_time_off.sql`, `lockedin/timeoff.py`, `lockedin/routes/timeoff.py`, `tests/test_time_off.py`
- Modify: `lockedin/app.py` (register router), `tests/test_schema.py` (table list)

**Interfaces:**
- Produces (in `lockedin/timeoff.py`):
  - `CATEGORIES = ("run", "bike", "swim", "upper", "core", "lower", "all")`, `REGIONS = {"upper": ("arms", "back", "chest", "shoulders"), "core": ("core",), "lower": ("legs",)}`
  - `class Restriction(BaseModel): category: Literal[...]; until: date`
  - `class TimeOffIn(BaseModel): reason: Literal["vacation", "injury"]; label: str | None (≤60); start: date; restrictions: list[Restriction]` (1–7 items, unique categories, every `until >= start`)
  - `entries(conn, since: date | None = None) -> list[dict]` — `{id, reason, label, start, end, restrictions:[{category, until}]}`, `end` = max until, ordered by start; `since` filters `end >= since`
  - `create(conn, body: TimeOffIn) -> dict`, `update(conn, entry_id: int, body: TimeOffIn) -> dict`, `delete(conn, entry_id: int) -> None` (LookupError when missing)
  - `off_on(conn, day: date) -> dict[str, date]` — category → latest `until` covering `day`; `all` expands to every category (including `all` itself)
  - `away_on(conn, day: date) -> bool` — `"all" in off_on(...)`
  - `off_muscles(conn, day: date) -> dict[str, date]` — muscle key → until, for `upper`/`core`/`lower` off that day (join `muscles.region`)
  - `entry_on(conn, day: date) -> dict | None` — the entry covering `day` (latest start wins)
  - `back_from(conn, day: date, category: str, within_days: int) -> dict | None` — the entry whose restriction for `category` (or `all`) ended in the `within_days` days before `day`
  - `describe(off: dict[str, date]) -> str` — "no running until 17 Dec, no upper body until 2 Jan"; "everything off until 27 Dec" when `all`
- Routes: `GET /api/time-off` (current and upcoming), `POST /api/time-off` (201), `PATCH /api/time-off/{id}`, `DELETE /api/time-off/{id}` (204), owner-only.

- [ ] **Step 1: Write the failing tests** in `tests/test_time_off.py`:
  - `test_off_on_expands_all_and_is_inclusive`: entry injury start 2026-12-03, `run` until 12-17, `upper` until 2027-01-02 → `off_on(12-17)` == `{"run": date(2026,12,17), "upper": date(2027,1,2)}`; `off_on(12-18)` == `{"upper": ...}`; `off_on(12-02)` == `{}`.
  - `test_vacation_all_means_away`: vacation 12-20, `all` until 12-27 → `away_on(12-27)` is True, `off_on(12-24)` has all 7 keys.
  - `test_overlap_takes_the_union_and_latest_until`: the two entries above plus a second `run` until 12-24 → `off_on(12-20)["run"] == date(2026,12,27)` (from `all`).
  - `test_off_muscles_by_region`: `upper` off → `off_muscles` keys == every muscle in regions arms/back/chest/shoulders; no `quads`.
  - `test_describe`: → `"no running until 17 Dec, no upper body until 2 Jan"`; all → `"everything off until 27 Dec"`.
  - `test_api_crud_and_validation` (client): POST → 201 with `end`; PATCH changes `until`; DELETE → 204; POST with `until < start` → 422 with message "Every restriction must end on or after the start."; POST with no restrictions → 422.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_time_off.py -q` — FAIL (module missing).
- [ ] **Step 3:** Migration: table `time_off(id bigint identity pk, reason text check in ('vacation','injury'), label text, start_day date not null, restrictions jsonb not null, created_at timestamptz default now())`, index on `start_day`; RLS on, revoke anon/authenticated, `grant select ... to coach_ro` + `coach_read` policy (as `20261028000002_ftp_history.sql`). Implement `lockedin/timeoff.py` and the router; add `"time_off"` to `tests/test_schema.py`.
- [ ] **Step 4:** Run the tests — PASS; run the full suite and ruff.
- [ ] **Step 5:** Commit `feat(time-off): entries with per-activity restrictions, and what's off on a day`.

### Task 2: Planner, focus tips and Muscles page

**Files:**
- Modify: `lockedin/focus/preferences.py`, `lockedin/plan/build.py`, `lockedin/routes/plan.py`, `lockedin/focus/suggest.py`, `lockedin/focus/mix.py`, `lockedin/focus/musclemap.py`
- Test: `tests/test_time_off_planning.py`

**Interfaces:**
- Consumes: `off_muscles`, `off_on`, `away_on`, `back_from` (Task 1).
- Produces: `load_preferences(conn, on: date | None = None) -> Preferences`; `Preferences.off_muscles: dict[str, date]` (empty by default). With `on`, those muscles are also in `avoid_muscles`, so `prefs_hash` changes when time off changes. Every caller in `plan/build.py`, `routes/plan.py`, `focus/suggest.py`, `focus/musclemap.py` passes the relevant Brussels day; `coach/prompt.py` keeps `on=None`.
- Planner: routine items whose primary muscle is in `prefs.off_muscles` get `skipped: True` and `reason: "Upper body is off until 2 Jan"` (region name from `REGIONS`). When every routine item is skipped, `build_plan` returns the plan with `note: "Upper body is off until 2 Jan; nothing left of this routine."` and no extras. The first 14 days after a gym restriction ends (`back_from(..., within_days=14)`), restricted lifts get the planner's eased change (−10%, `change: "eased"`, reason "Back after your time off: lighter to ease in") even if last done under 3 weeks ago.
- Focus: `session_suggestions` drops a sport that's off today; `gym_suggestions` and `session_suggestions` return `[]` when `away_on(today)`. Muscle map: muscles in `off_muscles(day)` get `"off_until": "2027-01-02"` and aren't counted as low.

- [ ] **Step 1: Write the failing tests:** `test_planner_skips_restricted_exercises` (routine with Bench + Squat, `upper` off today → Bench skipped with that reason, Squat planned); `test_planner_says_when_nothing_is_left` (all-upper routine → `note` as above); `test_first_days_back_are_eased` (Bench last done 10 days ago, restriction ended yesterday → Bench `change == "eased"`, weight 10% lower rounded down to the step); `test_saved_plan_rebuilds_when_time_off_changes` (build, add entry, GET plan → rebuilt); `test_focus_tips_skip_restricted_and_away` (run off → no run suggestion; away → both lists empty); `test_muscle_map_says_off_until` (chest has `off_until` and isn't in the low list).
- [ ] **Step 2:** Run them — FAIL.
- [ ] **Step 3:** Implement as in Interfaces.
- [ ] **Step 4:** Run them, the full suite and ruff — PASS.
- [ ] **Step 5:** Commit `feat(time-off): planner, focus tips and muscle map leave restricted work out`.

### Task 3: Agenda, Zwift feed and session notes

**Files:**
- Modify: `lockedin/agenda/store.py`, `lockedin/agenda/detail.py`, `lockedin/routes/agenda.py`
- Test: `tests/test_time_off_agenda.py`

**Interfaces:**
- Consumes: Task 1 helpers; `lockedin.timeoff.REGIONS`.
- Produces:
  - `item_category(conn, item) -> str | None` in `lockedin/timeoff.py` — sport `run`/`bike`/`swim` → itself; gym with a routine → the region category (`upper`/`core`/`lower`) holding more than half of the routine's last working sets by primary muscle, else `None`; rest/other → `None`.
  - Each agenda item dict gains `"clash": "Running is off until 17 Dec" | None`.
  - `week(...)` gains `"time_off": [{"day": "2026-12-03", "reason": "injury", "label": "Knee operation", "text": "no running, no upper body"}]` for days of that week inside an entry.
  - `create`/`update` with `source == "coach"` raise `ValueError("Running is off until 17 Dec, so I can't plan it then.")` for a clashing item; manual creates succeed and the route returns the item with `clash` set.
  - `zwift_feed` leaves out items on days when `bike` is off.
  - `detail(...)["easy_back"]`: `"First two weeks back after your time off: keep it easy."` for run/bike/swim items within 14 days after that category's restriction ended, else `None`.

- [ ] **Step 1: Write the failing tests:** coach create refused with that message; manual create → 201 with `clash`; existing item flagged after an entry is added (never deleted); week has `time_off` days; Zwift feed omits the bike-off day; first day back (`until + 1`) not refused and `easy_back` set; day 15 after → `easy_back` None; gym routine 70% chest during `upper` → refused for the coach.
- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement. **Step 4:** Run, full suite, ruff — PASS.
- [ ] **Step 5:** Commit `feat(time-off): the agenda flags clashes, the coach can't plan them, Zwift skips bike-off days`.

### Task 4: Coach

**Files:**
- Modify: `lockedin/coach/tools.py`, `lockedin/coach/prompt.py`
- Test: `tests/test_coach_time_off.py`

**Interfaces:**
- Consumes: `TimeOffIn`, `create`, `update`, `delete`, `entries`, `describe` (Task 1).
- Produces: tool `save_time_off` with input `{"action": "create" | "update" | "delete", "id"?: int, "entry"?: TimeOffIn-shaped}` and the same "only after the owner clearly agreed" wording as `save_goal`; result is the saved entry or `{"deleted": id}`; validation errors come back as tool errors in plain words. The per-turn context lists current and upcoming entries ("Time off: Knee operation from 3 Dec: no running until 17 Dec, no upper body until 2 Jan"). The system prompt gains: read the entry back in plain words and ask before saving; turn "for 15 days" / "a month" into dates (until = start + 14 days / same day next month − 1) and ask when the start is unclear; never plan or suggest restricted activities in a window, offer allowed ones; for 14 days after a run/bike/swim restriction ends plan that sport easy only (no intervals, run HR zone ≤ 2, Zwift parts ≤ 75% FTP); no medical advice about recovery — point to the surgeon or physio. The schema text in `tools.py` documents `time_off`.

- [ ] **Step 1: Write the failing tests:** `execute_tool("save_time_off", create ...)` stores the entry; `update` and `delete` work; invalid entry → error text, nothing stored; the context string includes the entry's description; the system prompt contains "surgeon or physio" and "Save?".
- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement. **Step 4:** Run, full suite, ruff — PASS.
- [ ] **Step 5:** Commit `feat(coach): record time off after agreement, plan around it, no medical advice`.

### Task 5: Streak, comeback card, Overview line

**Files:**
- Modify: `lockedin/focus/consistency.py`, `lockedin/routes/overview.py`
- Test: `tests/test_time_off_overview.py`

**Interfaces:**
- Consumes: `entries`, `off_on`, `back_from`, `describe` (Task 1).
- Produces:
  - `week_streak`: a protected week (4+ of its days inside any entry) counts when it has `STREAK_MIN_SESSIONS` sessions, else it's skipped over without breaking the streak.
  - `comeback(...)` result gains `title: str`: "Back from vacation" when the break overlapped a vacation, else the generic title. New: in the 14 days after an injury restriction ended, `/api/overview` returns `back_from: {"title": "Back from your operation", "label": "Knee operation"}` even without a 7-day break (use the label when set: "Back from: Knee operation").
  - `/api/overview` gains `time_off_today: "no running until 17 Dec, no upper body until 2 Jan" | "Vacation until 27 Dec" | None`.

- [ ] **Step 1: Write the failing tests:** streak of 3 weeks + a protected week with 0 sessions + this week with 2 → streak 4; a protected week with 2 sessions counts; an unprotected empty week still breaks; `time_off_today` text; `back_from` within 14 days after the injury restriction ends, gone on day 15.
- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement. **Step 4:** Run, full suite, ruff — PASS.
- [ ] **Step 5:** Commit `feat(time-off): protected streak weeks, back-from cards, today's line`.

### Task 6: Forecast on training time

**Files:**
- Modify: `lockedin/forecast/goals.py`, `lockedin/forecast/trend.py`, `lockedin/forecast/ahead.py`, `lockedin/forecast/__init__.py`
- Test: `tests/test_forecast_time_off.py`

**Interfaces:**
- Consumes: `off_on`, `entries`, `item_category` (Tasks 1, 3).
- Produces:
  - `goal_category(conn, now, goal, kind) -> str | None` in `forecast/goals.py`: lift goals → region of the lift's primary muscle (`upper`/`core`/`lower`), FTP/bike → `bike`, run → `run`, swim → `swim`, body → `None`.
  - `trend.fit(points, today, off_days: set[date] = frozenset())` and `trend.project(t, weeks, flatten, off_days: set[date] = frozenset(), settle_days: int = 14)`: x-values count only days not in `off_days` (training time); projection steps calendar weeks but adds gain only for training days after each off window's `settle_days`. Defaults keep today's behaviour exactly.
  - Goal history drops points on off days of its category (or away days).
  - `fitness_ahead` adds no planned load for items whose `item_category` is off on their day.
  - `forecast()` gains `"time_off": [{"start": "2026-12-03", "end": "2027-01-02", "reason": "injury", "label": "Knee operation"}]` (entries ending after 26 weeks ago) for chart shading.

- [ ] **Step 1: Write the failing tests:** a steady bench trend with an `upper` month in the past fits the same slope (±10%) as without the gap; a future `upper` window pushes the ETA back by at least the window plus 14 days; a 5k goal is unaffected by an `upper` window; fitness ahead has no load on a clashing day; `forecast()["time_off"]` lists the entry; all existing forecast tests still pass unchanged.
- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement. **Step 4:** Run, full suite, ruff — PASS.
- [ ] **Step 5:** Commit `feat(forecast): goals forecast on training time; time off pauses the trend`.

### Task 7: Web app

**Files:**
- Create: `web/src/pages/agenda/TimeOffCard.tsx`, `web/src/lib/timeoff.ts`, `web/src/pages/agenda/TimeOffCard.test.tsx`
- Modify: `web/src/pages/Agenda.tsx` (card, band, clash flag, manual-add warning), `web/src/pages/Overview.tsx` (today line, back-from card), `web/src/pages/Muscles.tsx` (off until), `web/src/pages/session/*` (`clash`, `easy_back` notes), `web/src/pages/Plan.tsx` (skipped reason, `note`), `web/src/pages/forecast/*` (shade `time_off` windows), `web/src/lib/types.ts`, `README.md` (new section "12. Time off", Agenda and Forecast mentions)

**Interfaces:**
- Consumes: the API shapes from Tasks 1, 3, 5, 6 exactly as named there.
- Produces: the Time off card (list of current and upcoming entries as "Operation · from 3 Dec · no running until 17 Dec, no upper body until 2 Jan", edit, delete with confirm; add/edit form: reason, label, start, each category "fine" / "off until [date]", and for vacation a shortcut "Everything off from … to …"); week-view days inside a window show a thin band with `time_off[].text`; items with `clash` show it in muted warning style; a manual add that comes back with `clash` shows it once.

- [ ] **Step 1: Write the failing tests:** card lists an entry with that exact line; the vacation shortcut posts `{reason: "vacation", restrictions: [{category: "all", until}]}`; editing posts a PATCH; Agenda shows the band and a clash line; Overview shows `time_off_today`; Muscles shows "Off until 2 Jan"; Forecast renders with `time_off` present.
- [ ] **Step 2:** Run `npx vitest run` — FAIL. **Step 3:** Implement. **Step 4:** `npx tsc -b`, `npx vitest run`, `npm run lint`, `npm run build` — all pass.
- [ ] **Step 5:** Commit `feat(web): time off card, bands and notes across the app`.

### Task 8: Ship

- [ ] **Step 1:** Full checks: `.venv/bin/ruff check .`, `.venv/bin/python -m pytest -q`, and the four web checks — all pass.
- [ ] **Step 2:** Ask the owner, then `supabase db push` (the migration from Task 1) before anything reaches `main` on GitHub.
- [ ] **Step 3:** Commit any remaining changes; push only when the owner says so.
