# LockedIn Plan 7: Agenda Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A week agenda the coach (after agreement) and the owner can fill and edit. Zwift workouts land in the owner's Zwift folder via the Mac sync, and sessions tick off automatically.

**Architecture:**
- **`lockedin/agenda/`:**
  - `zwo.py`: block validation (pydantic), `.zwo` rendering, file names, summaries
  - `store.py`: CRUD, week listing, tick-off matching, Zwift sync feed
- **Routes:** `lockedin/routes/agenda.py` (owner CRUD), plus a sync-only router for the Zwift feed.
- **Coach:** the tools gain `get_agenda`/`save_agenda` (pydantic-validated), and the turn context shows today and tomorrow.
- **Mac sync:** `sync/fit_sync.py` gains a stdlib workouts step with a manifest.
- **Frontend:** an `Agenda` page, an Overview Today card, and nav with a phone "More" menu.

**Spec:** `docs/superpowers/specs/2026-10-26-lockedin-agenda-design.md`

## Global Constraints

- **Weeks:** Monday–Sunday, Brussels. `?week=` takes any date and snaps to its Monday.
- **Sports:** `gym|bike|run|swim|rest|other`. `title` 1–80 chars, `note` ≤ 500.
  - **Gym:** `routine` must be one of the planner's routines (Hevy titles of the last 60 days, `plan.routines.routines`). Otherwise 422 listing the valid names.
  - **Zwift blocks** only on bike items.
- **Blocks** (our API):
  - `warmup|cooldown {duration_s, from_power, to_power}`
  - `steady {duration_s, power}`
  - `intervals {repeat, on_s, off_s, on_power, off_power}`
  - `free {duration_s}`
  - **Limits:** powers 0.3–1.6, durations 10–14400 s, `repeat` 1–30, ≤ 30 blocks, total ≤ 6 h.
  - **ZWO mapping:** `Warmup`/`Cooldown` `PowerLow=from_power`, `PowerHigh=to_power` (Zwift ramps from PowerLow to PowerHigh); `SteadyState Power`; `IntervalsT Repeat/OnDuration/OffDuration/OnPower/OffPower`; `FreeRide Duration`.
- **Zwift output:**
  - ZWO `<name>` is `YYYY-MM-DD Title`.
  - File name is `YYYY-MM-DD Title.zwo`, with `[^A-Za-z0-9 ._()×x-]` replaced by `-` and trimmed to 80 chars.
  - Text is XML-escaped.
- **Zwift feed:** `POST /api/agenda/zwift/sync` (sync token only; new `require_sync` in `auth.py`):
  - serves bike items with blocks, `day >= today` (Brussels)
  - returns `[{item_id, filename, content}]`
  - sets `zwift_synced_at = now()` on the served items
- **Zwift status:** an edit that changes `title`, `note`, `day` or `zwift` resets `zwift_synced_at`.
  - `zwift_status`: `"synced"` if synced, `"pending"` if not, `null` for past days or no blocks.
- **Tick-off** (computed on read):
  - Counted activities on the item's Brussels day:
    - **gym** with a routine: a gym session whose Hevy title equals it
    - **gym** without a routine: any gym session
    - **bike**: any bike activity
    - **run / swim**: that sport
    - **rest / other**: never
  - Each activity ticks at most one item. Items with a routine match first, then by `sort`, then `id`.
- **Watts:** `round(power * ftp_at(conn, now))`. Without an FTP, percentages.
- **Coach:**
  - `save_agenda {changes: [{op: "add"|"update"|"delete", id?, day?, sport?, title?, note?, optional?, routine?, zwift?: {blocks}}]}`, at most 30 changes, applied in one transaction. Returns the changed items.
  - Prompt: only after explicit agreement; Zwift sessions as structured blocks, not XML; no dates in titles.
  - `get_agenda {from?, to?}`, defaulting to this week and next.
  - The turn context lists today's and tomorrow's items.
- **Mac sync (stdlib, Python 3.9):**
  - After uploads, call the feed only if exactly one numeric subfolder exists in `ZWIFT_WORKOUTS_DIR` (default `~/Documents/Zwift/Workouts`) or that setting points straight at it.
  - Write changed files, delete manifest-listed files that are no longer served, and keep `.lockedin-workouts.json`.
  - Never touch other files. Errors here never block uploads.
  - Log line gains `, Zwift workouts +N -M`.
  - The plist `StartInterval` becomes 900.
- **UI:** Night Shift, reduced motion, no guilt wording, 375 px with no overflow.
  - Sidebar: Agenda second.
  - Phone tab bar: Home, Agenda, Coach, Activities, Muscles, More (a menu with Trends, Body, Import).

## Review Focus

1. **Dangerous file names from titles** (`../../x`, slashes, emoji, 200 chars) → a safe, short file name inside the workouts folder. → Task 1 test + Task 3 test (the script rejects names with `/` or a leading `.`).
2. **A manifest listing a file the user since replaced with their own** (same name, different content):
   - The script only deletes a manifest file if its content hash still matches what it wrote; otherwise it leaves the file and drops it from the manifest.
   - → Task 3 test.
3. **Two items on one day, both bike, one activity** → only the first ticks. → Task 1 test.
4. **The coach sends garbage blocks** (negative durations, a power of 5, 100 blocks, wrong type) → `is_error` result with a clear message and no partial writes. → Task 2 test.
5. **A DST week** (25 Oct 2026): items and activities on Sunday the 25th match by Brussels day. → Task 1 test.

---

### Task 1: Agenda data, ZWO, API, tick-off, sync feed

**Files:**
- Create: `supabase/migrations/20261027000004_agenda.sql`, `lockedin/agenda/__init__.py`, `lockedin/agenda/zwo.py`, `lockedin/agenda/store.py`, `lockedin/routes/agenda.py`, `tests/test_agenda.py`
- Modify: `lockedin/auth.py` (`require_sync`), `lockedin/app.py`, `tests/test_schema.py`

**Interfaces:**
- **`zwo.py`:**
  - pydantic `Block` (discriminated on `type`), `ZwiftWorkout(blocks: list[Block])` with the limits above
  - `render(title, day, note, workout) -> str`
  - `filename(title, day) -> str`
  - `duration_s(workout) -> int`
  - `summary(workout, ftp) -> str`, e.g. `"65′ · 3 × 10′ at 151 W"`: the hardest block, by power × duration
- **`store.py`:**
  - `ItemIn` (pydantic) for create, and a partial update model
  - `week(conn, now, week_date) -> {week_start, today, items}`
  - `create(conn, now, data, source)`, `update(conn, now, id, changes)`, `delete(conn, id)`
  - `range_items(conn, now, start, end)` (for the coach)
  - `zwift_feed(conn, now) -> list[dict]`
  - `ValueError` for validation problems, `LookupError` for an unknown id
- **Routes:**
  - `GET /api/agenda?week=`
  - `POST /api/agenda` (201)
  - `PATCH /api/agenda/{id}`
  - `DELETE /api/agenda/{id}` (204)
  - `POST /api/agenda/zwift/sync`

- [ ] **Step 1: Failing tests** in `tests/test_agenda.py`:
  - **ZWO:** rendering the Sweet Spot workout gives XML that parses and has `IntervalsT Repeat="3" OnDuration="600" OffDuration="300" OnPower="0.9" OffPower="0.55"` and `<name>2026-10-29 Sweet Spot 3x10</name>`. A note with `<&>` is escaped.
  - **File names:** `filename("../../evil/x", day)` has no `/` and doesn't start with `.`; a 200-char title gives ≤ 80 chars plus `.zwo`.
  - **Block validation:** power 5 → error; 31 blocks → error; total of 7 h → error; a negative duration → error.
  - **Summary:** with FTP 168, the sweet spot gives `"65′ · 3 × 10′ at 151 W"`; with no FTP, `"65′ · 3 × 10′ at 90%"`.
  - **CRUD via the client:**
    - create a gym item with an unknown routine → 422 naming the valid routines; with a valid one (fixture Hevy title) → 201
    - a bike item with blocks → 201; patch its day → `zwift_synced_at` reset; delete → 204, and GET no longer has it
    - Zwift blocks on a run → 422
  - **Week:** `GET /api/agenda?week=2026-10-29` → `week_start == "2026-10-26"`, items sorted by day, sort, id.
  - **Tick-off:**
    - A Zwift ride on Thu ticks the bike item; a gym session titled "Rug - Bicep" ticks the matching gym item and not a routine-less gym item on the same day.
    - Two bike items with one ride → only the first ticks.
    - A rest item never ticks.
    - An item on Sun 25 Oct 2026 with a ride at 22:30 UTC that day ticks (DST).
  - **Zwift feed:**
    - With the sync token, it returns today's and future bike-with-blocks items (not past ones) with `filename` and `content`, and sets `zwift_synced_at` (GET then shows `zwift_status == "synced"`).
    - An owner token → 401. No token → 401.
  - **Schema:** `test_schema` includes `agenda_items`, and `coach_ro` can select it.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `.venv/bin/pytest` passes.
- [ ] **Step 5: Commit** `feat(agenda): agenda items, Zwift workout files, tick-off and sync feed`.

### Task 2: Coach tools for the agenda

**Files:**
- Modify: `lockedin/coach/tools.py`, `lockedin/coach/prompt.py`
- Test: `tests/test_coach_agenda.py`

- **`validate()`:** supports `array`, `number` and `boolean` at the top level; nested validation is done by the pydantic models in `store`.
- **`get_agenda`:** returns JSON items with done state.
- **`save_agenda`:**
  - Applies changes in a savepoint: any error rolls back all changes and returns `is_error` with the message.
  - Returns the changed items.
- **`SCHEMA_TEXT`:** documents `agenda_items`.
- **`turn_context`:** adds "Agenda today: …; tomorrow: …" (or "nothing planned").

- [ ] **Failing tests:**
  - `save_agenda` with 3 adds (gym routine, Zwift blocks, rest) → stored, `source == "coach"`.
  - An update moving a day works. A delete works.
  - A garbage block (power 5) in the second of two changes → `is_error`, and the first change was not stored.
  - An unknown routine → `is_error` naming the valid ones.
  - `get_agenda` lists items with `done`.
  - `turn_context` mentions today's item title.
- [ ] Implement, run the full pytest, then commit `feat(coach): plan and change the agenda after agreement`.

### Task 3: Mac sync writes Zwift workouts

**Files:**
- Modify: `sync/fit_sync.py`, `sync/com.lockedin.fitsync.plist.template` (`StartInterval` 900), `tests/test_fit_sync.py`

- **`workouts_dir(cfg) -> Path | None`, with `ZWIFT_WORKOUTS_DIR` handling:**
  - unset: use `~/Documents/Zwift/Workouts`
  - a numeric folder name: use it as given
  - otherwise: its single numeric subfolder
  - none or several: `None`, plus a warning
- **`sync_workouts(cfg, http) -> (written, removed, warnings)`:**
  - Manifest `{filename: sha256}`. Files are only written when the content changed.
  - It deletes manifest files that are no longer served, only if their hash still matches; otherwise it keeps the file and forgets it.
  - Served names containing `/` or `\`, or starting with `.`, are rejected with a warning.
- **`SyncReport`** gains `workouts_written` and `workouts_removed`. `run()` calls `sync_workouts` once after the uploads.

- [ ] **Failing tests:**
  - It writes two served workouts and creates the manifest.
  - A second run with the same content → 0 written.
  - The server stops serving one → it's removed.
  - A user-modified file → kept and dropped from the manifest.
  - A user's own unrelated `.zwo` → untouched.
  - A served name `../x.zwo` → rejected.
  - No numeric folder → no HTTP call, and a warning.
  - A feed error → upload results still reported.
- [ ] Implement, run the pytest, then commit `feat(sync): Mac sync drops planned Zwift workouts into Zwift`.

### Task 4: Agenda UI, Today card, nav

**Files:**
- Create: `web/src/pages/Agenda.tsx`, `web/src/lib/agenda.ts` (types, `weekDays(weekStart)`, `zwiftShape(blocks)` → bars), `web/src/lib/agenda.test.ts`, `web/src/pages/Agenda.test.tsx`
- Modify: `web/src/App.tsx`, `web/src/components/Layout.tsx` (Agenda second; phone tab bar with More), `web/src/pages/Overview.tsx` (Today card), `web/src/styles.css`

**Behaviour:** as in the spec's Goals.
- **Item sheet:** a dialog with title, note, day, optional, delete and the Zwift shape.
- **Add form:** sport, routine select (from `/api/plan/days`), title, note, optional.
- **Errors:** 422 messages show inline.
- **Zwift status text:** "In Zwift ✓", or "Goes to Zwift at the next Mac sync (restart Zwift to see it)".

- [ ] **Failing tests:**
  - `weekDays` for `2026-10-26` → 7 ISO dates across the DST-safe range.
  - `zwiftShape` → bars with relative widths and heights.
  - Agenda page (jsdom, mocked api):
    - It renders 7 days with items; a gym item has a "Plan it" link to `/plan?day=…`.
    - **+ Add** on Wednesday posts the right body.
    - Opening an item and changing its day sends a PATCH with `{day}`.
    - Delete asks for confirmation, then sends DELETE.
  - Layout: the phone **More** menu lists Trends, Body and Import.
- [ ] Implement. Run `npx vitest run` and `npm run build`.
- [ ] **Playwright on the local stack:**
  - Create items via the API and see them in the week. Add one through the UI and move one.
  - The Overview Today card shows.
  - The phone More menu works.
  - 375 px and 1440 px with no overflow or console errors.
  - Look at the screenshots.
- [ ] **Commit** `feat(web): agenda week view, Today card and phone More menu`.

### Task 5: Docs and wrap-up

- [ ] README "Agenda" section:
  - how the coach fills it and how to edit it
  - the Zwift files and the restart
  - ticking off
  - **Re-run `sync/install.sh`** to get the 15-minute interval
  - the deploy order
- [ ] Run the full suites and commit.
