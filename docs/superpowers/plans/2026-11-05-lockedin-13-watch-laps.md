# Per-block results from the watch's own laps: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A run's verdict and session page show exact per-block results from the laps the watch records, instead of placing the plan on the run's data.

**Architecture:** The FIT parser keeps laps; the importer stores them in `activities.laps` and fills them in for known files. `lockedin/agenda/blocks.py` turns laps plus the plan's steps into blocks; `detail()` and the verdict's facts use it. The old `step_results` matching is removed.

**Tech Stack:** FastAPI, SQLAlchemy `text()`, fitdecode, Supabase migrations, pytest; React + Vitest; `sync/fit_sync.py` (standard library only).

**Spec:** [docs/superpowers/specs/2026-11-04-lockedin-workout-verdict-design.md](../specs/2026-11-04-lockedin-workout-verdict-design.md), "Watch laps"

## Global Constraints

- **No worktrees.** Work directly on `main`; commit per task; don't push, don't run `supabase db push`.
- **Local DB:** apply the migration with `supabase migration up --local`.
- **Real files stay private.** Never commit a file from the owner's HealthFit folder. Tests use synthetic samples. A read-only local check against `~/Library/Mobile Documents/iCloud~com~altifondo~HealthFit/Documents/2026-11-04-183552*.fit` is expected and goes in the report.
- **That file's expected result:** 8 laps; the blocks are 8:00 at 5:31/km and 164 bpm, 8:00 at 5:51/km and 163 bpm, 8:00 at 5:56/km and 163 bpm; warm-up 10:00, 135 bpm; `wkt_step_index` 0,1,2,1,2,1,2,4; intensity warmup, active, recovery, active, recovery, active, recovery, cooldown.
- **Nothing guessed:** a run without step laps has no blocks. The verdict then uses km splits, zones and totals.

## Review Focus

1. **A free run, or a run from a different workout on the watch:** no invented comparison with the plan (Task 2 test).
2. **A step skipped or cut short by pressing next:** the block shows what really happened; nothing later is shifted (Task 2 test).
3. **Re-uploading a known file:** fills laps only when null, deletes that workout's verdict only when laps with steps were found, and is safe to repeat (Task 1 test).
4. **A file with no laps, or laps without step indexes:** stored as such; the page and verdict are as before (Task 1 and 2 tests).
5. **A multisport file:** each leg gets its own laps only (Task 1 test).

---

### Task 1: Keep and store the laps

**Files:**
- Create: `supabase/migrations/20261105000001_activity_laps.sql`
- Modify: `lockedin/fit/parse.py`, `lockedin/fit/importer.py`, `samples/make_ingest_samples.py` (a synthetic watch workout with step laps), `sync/fit_sync.py`, `README.md` (section 13 or the Mac sync section), `lockedin/coach/tools.py` (one schema line)
- Test: `tests/test_fit_laps.py`, `tests/test_fit_sync.py`

**Interfaces:**
- Produces:
  - `ParsedFit.laps: list[dict]`, each `{"start_s", "timer_s", "elapsed_s", "distance_m", "avg_hr", "avg_speed", "intensity", "trigger", "step_index"}`, any of them null when absent. `start_s` is seconds from the activity's start.
  - Column `activities.laps jsonb`, null by default. Written at import as a list, `[]` when none. Check whether `coach_ro`'s existing select covers the new column, and mention it in the coach's schema text for `activities`.
  - `import_fit`, for a known `ok` file whose activity has null `laps`: parse it, write the laps (matching a multisport file's legs by `source_ref`, `sha` and `sha#2`), and if any lap has a `step_index`, delete that activity's `workout_verdicts` row. Still returns `duplicate`.
  - `python3 sync/fit_sync.py --refresh-days N`: uploads HealthFit files from the last N days again, whatever the saved state says, once, and reports how many. The normal run is unchanged.

- [ ] **Step 1: Write the failing tests:** `test_laps_are_parsed` (the synthetic sample's values), `test_multisport_laps_stay_with_their_leg`, `test_no_laps_is_empty`, `test_import_stores_laps`, `test_known_file_fills_null_laps_and_deletes_the_verdict`, `test_known_file_with_laps_is_not_read_again` (a parse failure on a second upload isn't reached), `test_filling_laps_without_steps_keeps_the_verdict`, and in `tests/test_fit_sync.py` `test_refresh_uploads_recent_known_files_only`.
- [ ] **Step 2: Run them and check they fail.** `.venv/bin/python -m pytest tests/test_fit_laps.py tests/test_fit_sync.py -q`.
- [ ] **Step 3: Implement.** Laps are collected in `_parse` alongside records and assigned to the session whose time range holds the lap's start. In `import_fit`, an error while filling laps on a known file must still return `duplicate`, logged, never an error. `make samples` regenerates samples; commit only the new synthetic file.
- [ ] **Step 4: Run them and check they pass,** then the whole suite, and the read-only check of the real file's parsed laps against the constraint above.
- [ ] **Step 5: Commit** `feat(fit): keep the laps a watch records, and fill them in for known files`.

### Task 2: Blocks, for the session and the verdict

**Files:**
- Create: `lockedin/agenda/blocks.py`
- Modify: `lockedin/agenda/detail.py`, `lockedin/agenda/actual.py` (`ACTIVITY` gains `laps`), `lockedin/verdict/facts.py`, `lockedin/verdict/write.py`
- Test: `tests/test_blocks.py`, `tests/test_verdict_facts.py`, `tests/test_verdict_write.py`, `tests/test_session_detail.py`

**Interfaces:**
- Consumes: `activities.laps`; `expand(steps)`; the zone ranges used by `lockedin/verdict/facts.py`.
- Produces:
  - `blocks(laps: list | None, steps: dict | None, zones: dict) -> dict | None`: `{"follows_plan": bool, "rows": [{"kind", "repeat", "seconds", "metres", "pace_s_per_km", "avg_hr", "planned_goal", "planned_target", "in_target"}]}`, or None when no lap has a `step_index`.
  - Kinds: `warmup`→warmup, `active` and `interval`→work, `recovery` and `rest`→recovery, `cooldown`→cooldown; anything else→work. Pace is `1000 / avg_speed`, else from timer and distance, else null.
  - `follows_plan`: steps exist, there are no more laps than expanded steps, and each lap's kind equals the expanded step's kind at its position. When false, `planned_goal`, `planned_target`, `in_target` and `repeat` are null.
  - `detail()`: for a run, `actual["blocks"]`; and on a run with `targets.steps`, split rows have no `status`.
  - `facts()`: key `blocks` replaces `step_results`; `matched_by` is removed.
  - Removed: `step_results` and its helpers and constants in `facts.py`, with their tests. `moving_seconds` stays in `actual.py`, as `splits` uses it.

- [ ] **Step 1: Write the failing tests:** `test_blocks_follow_the_plan` (the real file's shape as synthetic values, with `in_target` false for 5:31 against 5:45–6:00 and true for 5:51), `test_zone_target_is_judged_on_bpm`, `test_free_run_has_no_blocks`, `test_other_workout_is_not_judged`, `test_step_cut_short_shows_what_happened`, `test_run_stopped_early_still_follows`, `test_no_steps_in_plan_still_shows_blocks_unjudged`; in `test_session_detail.py`, blocks present and split status gone on a stepped run, split status kept on a plain run; in `test_verdict_facts.py`, `blocks` in the facts and no `step_results`.
- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement,** and rewrite `SYSTEM` in `write.py`:
  - Start with how it went against the plan, the main point first. 2 to 4 sentences; keep it short.
  - `blocks` holds the watch's own laps and is exact: judge a stepped run on its work blocks. Name blocks ("first block", "the last two") rather than km.
  - km splits mix blocks and recoveries: use them only when `blocks` is null.
  - `follows_plan` false: say the run didn't follow the plan's steps, and don't judge the blocks against the targets.
  - Mention missing data only if it changes the verdict. Never talk about how the data was collected or matched, or say "no per-block breakdown".
  - Remove the lines about `step_results` and `matched_by`. Keep the units, the swim pace line, and everything else.
- [ ] **Step 4: Run them and check they pass,** then the whole suite and ruff, and the read-only check: `blocks()` on the real file's laps with steps of 10′, 3 × (8′ at 5:45–6:00, 2′), 10′ gives `follows_plan` true and the constraint's numbers.
- [ ] **Step 5: Commit** `feat(verdict): judge a run on the watch's laps, not on a guess`.

### Task 3: The blocks on the session page

**Files:**
- Modify: `web/src/lib/session.ts`, `web/src/pages/session/ActualSection.tsx`, `web/src/pages/Session.test.tsx`, `README.md`

**Interfaces:**
- Consumes: `actual.blocks` from Task 2.

- [ ] **Step 1: Write the failing tests:** a run with blocks shows a "Blocks" card above Splits, with a row per lap: name ("Warm-up", "Block 1", "Recovery", "Cool-down"), time, pace, heart rate, and for work blocks "On target", "Faster" or "Slower" using the same words and colours as Splits (from `in_target` and the block's target); `follows_plan` false shows the rows without those words plus "This run didn't follow the plan's steps."; no blocks means no card; a split row without `status` shows no label.
- [ ] **Step 2: Run them and check they fail.** `npm --prefix web test -- --run`.
- [ ] **Step 3: Implement.** Follow the Splits table's markup. Update the README's watch section: the session page shows each block from the watch's laps, and the one-time `python3 sync/fit_sync.py --refresh-days 30` for older runs.
- [ ] **Step 4: Run them and check they pass.** `npm --prefix web test -- --run && npm --prefix web run lint && npm --prefix web run build`, then the Python suite.
- [ ] **Step 5: Commit** `feat(web): a run's blocks on its session page`.
