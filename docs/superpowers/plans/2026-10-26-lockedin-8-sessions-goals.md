# LockedIn Plan 8: Today, Session Pages, Goals Everywhere Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- A Today to-do list on the Overview.
- Clear "done" in the agenda.
- A full session page with the plan before and plan-vs-actual after (Zwift, gym, run, swim).
- Goals steering the focus tips, planner, muscle map, agenda and coach, with progress bars.

**Architecture:**
- **New `lockedin/goals/`:** `areas` and `goal_lift`, plus `progress.py`.
- **New `lockedin/agenda/detail.py`:** plan breakdowns and actual comparisons, built on the existing streams, zones, FTP and tick-off.
- **Agenda items** gain `targets` and `goal_id`.
- **Focus, planner and muscle map** get goal hooks.
- **Frontend:** a new `/agenda/:id` page, a Today block, a goals card with progress, and done styling.

**Spec:** `docs/superpowers/specs/2026-10-26-lockedin-sessions-and-goals-design.md` (including "Settled after the builder check").

## Global Constraints

- **Targets:**
  - `{distance_m?, duration_s?, pace_low?, pace_high?, hr_zone?}`, on run and swim items only.
  - Limits: distance 100–100000; duration 60–21600; run pace 150–720 s/km; swim pace 50–300 s/100 m; `pace_low` ≤ `pace_high`; `hr_zone` 1–5 (run only).
- **`goal_id`:** must reference an active goal. 422 otherwise (store raises `ValueError`).
- **On target:** |actual − target| ≤ 3% of the target. Labels: "On target", "Above", "Below".
- **Work parts:** steady, interval on, or ramp with an average fraction ≥ 0.75.
  - **Labels:** "Warm-up", "Cool-down", "Interval n" (interval on and steady parts ≥ 0.75), "Recovery", "Steady", "Free ride".
- **Formulas:**
  - Sweet-spot minutes: parts with an average fraction in [0.84, 0.97].
  - TSS estimate: Σ(dur_h × avg_frac² × 100); free rides count as 0.5.
- **Streams:** downsampled to ≤ 600 points, with 30 s smoothing for power and pace; done in the backend.
- **Splits:** per full km from the `distance` stream (cumulative metres), plus a last partial split if it's ≥ 200 m.
- **HR zones:** `hr_zone(hr, max_hr_at(ride start))` from `focus/zones.py`.
- **No guilt wording:** "close", "below", "not done", "skipped by you".
- **Goal areas:** `gym|bike|run|swim|body|general`.
- **Progress rules:** as in the spec, plus the settled rules.
- **UI:** Night Shift, reduced motion, 375 px with no overflow.

## Review Focus

1. **A done Zwift item whose ride is much shorter than the plan** (stopped after 2 intervals): the parts beyond the ride have no actual and show "not ridden", with no crash and no zero averages. → Task 3 test.
2. **A done run with no streams** (manual or summary-only FIT): totals only, no splits or zones, no crash. → Task 3 test.
3. **A goal text with several numbers** ("Bench 100 kg by March 2027 at 80 kg bodyweight"): uses the first number with the right unit, never "2027". → Task 1 test.
4. **Deleting a goal that agenda items reference:** the items keep working with `goal_id` null (fk set null). → Task 2 test.
5. **The session page for an item on a day with two bike rides:** shows the ride that ticked it (`activity_id` from tick-off), not the other one. → Task 3 test.

---

### Task 1: Goal areas, goal lifts, progress

**Files:**
- Create: `supabase/migrations/20261027000005_sessions_goals.sql`, `lockedin/goals/__init__.py`, `lockedin/goals/progress.py`, `tests/test_goal_progress.py`
- Modify:
  - `lockedin/coach/tools.py` (`save_goal` `area` enum; `get_goals` includes `progress`)
  - `lockedin/routes/plan.py` (`/api/goals/active` includes `area`, `exercise`, `progress`)

**Migration:**
- `goals.area`: map known variants (lower-case; containing "gym/strength" → gym, "bike/cycl/zwift" → bike, "run" → run, "swim" → swim, "body/weight" → body), else general. Add the check constraint.
- `agenda_items`: add `targets jsonb` and `goal_id bigint references goals(id) on delete set null`.

**Interfaces:**
- `goal_lift(conn, now, goal) -> str | None`
- `progress(conn, now, goal) -> dict | None` returning `{current, target, unit, label, fraction}`, with `fraction` 0–1.

- [ ] **Failing tests:**
  - **Lift:** "Bench 100 kg" with exercise set and a best e1RM of 96 → label "96 / 100 kg est. 1RM", fraction 0.96. The same goal without exercise, with bench as the only matching logged lift → the same result.
  - **Bike:** area bike "FTP 200 W" with an FTP override of 168 → "168 / 200 W".
  - **Run:** area run "Run a 10K" with the longest run 8.2 km → "8.2 / 10 km".
  - **Swim:** area swim "Swim 2 km" with the longest 1500 m → "1.5 / 2 km".
  - **Body:** "Weight 78 kg" with 82 at creation and now 80 → fraction 0.5. "Lose 5 kg" → None.
  - **Number picking:** "Bench 100 kg by March 2027 at 80 kg bodyweight" → target 100, not 2027.
  - **No number:** "Feel fitter" → None.
  - **API:** the active goals endpoint returns `progress`; `save_goal` with `area: "cardio"` → error.
- [ ] Implement. Run pytest. Commit `feat(goals): goal areas, goal lifts and measurable progress`.

### Task 2: Goals steer suggestions, planner, muscle map; agenda targets and goal links

**Files:**
- Modify:
  - `lockedin/focus/suggest.py` (rank goal-lift muscles first; `GymSuggestion.goal`)
  - `lockedin/focus/mix.py` (`SessionSuggestion.goal`; goal sessions)
  - `lockedin/routes/overview.py` (goal items first)
  - `lockedin/plan/build.py` (+1 set rule; adds ranking)
  - `lockedin/focus/musclemap.py` (`goals` per muscle)
  - `lockedin/agenda/store.py` (`targets` model, `goal_id` validation, output `goal` label and `targets`)
  - `lockedin/coach/tools.py` (schema: `targets`, `goal_id`), `lockedin/coach/prompt.py`
- Test: `tests/test_goals_everywhere.py`

- [ ] **Failing tests:**
  - **Gym focus:** with a bench goal and triceps low among other low muscles, `gym_suggestions` lists triceps (secondary of bench) first, its reason ends "· helps: Bench 100 kg", and `goal` is set.
  - **Run focus:** an active run goal with no run rule firing → `session_suggestions` includes "Steady run 40′" with `goal`; with a run rule firing, that suggestion carries the goal instead.
  - **Overview:** the focus puts goal items first.
  - **Planner extra set:**
    - Bench (goal lift) with 3 top sets last time → `sets == 4`, with "+1 set for your goal" in the reason.
    - With 4 last time → 4.
    - Comeback → no extra.
  - **Planner adds:** goal-lift muscles rank first among adds.
  - **Muscle map:** `muscle_map` gives triceps `goals == ["Bench 100 kg"]`.
  - **Agenda:**
    - A run item with targets → stored and returned.
    - Targets on a bike item → 422.
    - `pace_low` > `pace_high` → 422.
    - `goal_id` of an achieved goal → 422.
    - Deleting the goal → the item's `goal_id` becomes null and the item still lists.
  - **Coach:** `save_agenda` with `targets` and `goal_id` works.
- [ ] Implement. Run pytest. Commit `feat(goals): goals steer focus tips, planner, muscle map and agenda`.

### Task 3: Session detail API

**Files:**
- Create: `lockedin/agenda/detail.py`, `tests/test_session_detail.py`
- Modify: `lockedin/routes/agenda.py` (`GET /api/agenda/{id}/detail`)

**Interface:** returns `{item, plan, actual}`.
- **`plan`**, by sport:
  - **bike with blocks:** `{kind: "zwift", ftp, parts: [{label, start_s, end_s, from_w, to_w, from_frac, to_frac, work}], duration_s, sweet_spot_min, tss_est}`. Without an FTP, the watts are null and the fractions show.
  - **run/swim:** `{kind: "targets", ...targets, hr_bpm: [lo, hi] | null}`.
  - **gym:** `{kind: "gym", routine, items: [...planner items]}`. Before: the current plan if built today, else `build_plan` for the item's day (future days use now). After: the saved plan for that day, else routine items as of `start − 1 min`.
  - **otherwise:** `{kind: "note"}`.
- **`actual`** (null unless done):
  - **Common:** `{activity_id, start_at, duration_s, distance_m, avg_power, np, tss, avg_hr, avg_pace_s_per_km, swim_pace_s_per_100m, swim_lengths, swim_strokes}`.
  - **Zwift:** `power: [[t, w]]`, `hr: [[t, bpm]]` (downsampled), `parts: [{label, target_w, avg_w, avg_hr, avg_cadence, status}]` (status null when not ridden), `intervals_on_target: bool | null`.
  - **Run:** `pace: [[t, s_per_km]]`, `splits: [{km, pace, avg_hr, status}]`, `zones: {1..5: seconds}` (null without max HR).
  - **Gym:** `rows: [{exercise, planned: {sets, reps, weight_kg, dumbbell} | null, done: [{kg, reps}], status: "done" | "close" | "skipped" | "skipped_by_you" | "added", extra: bool, goal}]`.
- **`result_line(item, actual)`:** shared with the week listing (each agenda item gains `result`).

- [ ] **Failing tests:**
  - **Zwift plan:** sweet spot parts (7 parts, labels, watts at FTP 168), sweet-spot minutes 30, `tss_est` ≈ 58.
  - **Zwift done:** a ride with power stream 151/149/153 in the intervals → statuses on target and `intervals_on_target`. A ride stopped at 22 min → interval 2 onward has `status` null (not ridden).
  - **Two rides one day:** the detail uses the ticked activity.
  - **Run plan:** `hr_bpm` from the max HR.
  - **Run done:** distance stream → splits (8 full + partial), zones sum to the duration. No streams → splits and zones null, totals present.
  - **Swim done:** totals.
  - **Gym:**
    - Done with a saved plan: a skipped extra → "skipped_by_you"; an exercise logged but not planned → "added"; a fully done one → "done"; fewer reps → "close".
    - Done without a saved plan → routine rows only.
  - **Result lines:** each sport's format.
  - **Errors:** an unknown id → 404; no token → 401.
- [ ] Implement. Run pytest. Commit `feat(agenda): session detail with plan vs actual`.

### Task 4: Frontend

**Files:**
- Create: `web/src/pages/Session.tsx`, `web/src/lib/session.ts` (formatters: `mmss`, `pace`, `statusLabel`), tests
- Modify:
  - `web/src/App.tsx` (`/agenda/:id`)
  - `web/src/pages/Agenda.tsx` (done/missed styling with the result line; click navigates; the edit sheet is removed and moved to Session)
  - `web/src/pages/Overview.tsx` (Today block, goals card with progress, goal tags on focus)
  - `web/src/components/FocusCard.tsx` (goal tag)
  - `web/src/pages/Muscles.tsx` (goal line)
  - `web/src/lib/types.ts`, `web/src/lib/agenda.ts`, `web/src/styles.css`

- **Session page:**
  - Uses `SeriesChart` patterns: the Zwift chart overlays target and HR; the run pace chart has a target band.
  - Tables as in the mockup.
  - Edit, Move (date input) and Delete (confirm).
- [ ] **Failing tests:**
  - `session.ts` formatters.
  - Session page (jsdom, mocked):
    - The before view lists the parts.
    - The after view shows interval statuses and a "Full activity" link.
    - The gym after view shows "skipped by you".
    - Edit day sends a PATCH.
  - Agenda: a done item shows its result line; clicking navigates to `/agenda/:id`.
  - Overview: Today shows "1 of 2 done", and the goals card shows the progress label.
- [ ] Implement. Run vitest and the build.
- [ ] **Playwright** on local data seeded through `save_agenda` plus fixture activities (a done ride with power, a done run with distance and HR streams, a done gym day):
  - Overview Today, the agenda done styling, and every session view.
  - 1440 px and 375 px with no overflow or console errors.
  - Look at the screenshots.
- [ ] **Commit** `feat(web): Today block, session pages, goal progress and tags`.

### Task 5: Docs and review

- [ ] README updates (Today, session pages, goals everywhere). Run the full suites and commit.
