# LockedIn Plan 6: Workout Planner, Preferences and Goals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before the gym, the owner picks one of their Hevy routines and gets it back with today's targets, at most one variety swap and up to two extras. The app respects their training preferences (left-out muscles, never-suggest exercises, notes) and their coach goals everywhere.

**Architecture:**
- **New package `lockedin/plan/`:**
  - `routines.py` learns routines from Hevy workout titles
  - `build.py` builds a plan from the routine, the focus engine and the preferences
  - `goals.py` ties goals to exercises
- **Preferences** live on `profile` and have their own `/api/preferences`.
- **Plans** live in `workout_plans`, with a freshness key (local date, source workout id, preferences hash).
- **Shared helpers:** focus-engine helpers become public where the planner needs them (no copies).
- **Frontend:** a `/plan` page (day picker, plan, preferences sheet), plus an Overview "Going to the gym?" card and a "Your goals" card. The Muscles page gets the "left out" style.

**Tech:** existing stack. Vitest with jsdom/RTL for page tests; Playwright for verification.

**Spec:** `docs/superpowers/specs/2026-10-26-lockedin-workout-planner-design.md` (read it, including "Settled after the builder check" and "Goals").

## Global Constraints

- **Routines:**
  - A routine is a workout title used at least once in the last 60 days by a counted gym session. Its exercises (in order) and its non-warm-up set counts come from the latest such workout.
  - Its key is the exact title.
- **Rep range and progression:**
  - Rep range 8–12. Ready to go up when every non-warm-up set at the top weight hit ≥ 12 reps.
  - Steps: barbell, machine, cable or other +2.5 kg; dumbbell +2 kg per dumbbell (+4 on a pair total); bodyweight +1 rep.
  - A bodyweight-tagged exercise logged with weight > 0 steps like a weighted lift (+2.5 kg).
  - Not ready: same weight, labelled "same weight, aim for one more rep".
- **Limits:** at most 1 variety swap and 2 adds per plan. Adds go in the "Extra, if you have time" block.
- **Day muscles:** the regions of the routine's primary muscles, plus the routine's secondary muscles.
- **Swap candidates:**
  - A routine exercise listed in the gym plateaus, not tied to an active goal, first in routine order.
  - Its replacement: same primary muscle, not in the routine, not never-suggest, its primary muscle not avoided. Prefer the owner's own (last 90 days), then library order.
- **Adds:** day muscles that are low in `muscle_coverage`, not hit as primary by the routine, and not avoided. Ranked like `gym_suggestions`, picked with `_pick`, never-suggest excluded.
- **Comeback** (`comeback()` not None): no steps ("Welcome back: same as last time"), no adds, no swap, no "missed" day.
- **Plan freshness:** a plan is reused only if `built_on` is today's local date, `source_activity_id` is unchanged and `prefs_hash` is unchanged; otherwise it is rebuilt.
- **Actions:**
  - Swap (any item) replaces it with the next alternative for the same primary muscle; routine items swap for today's plan only.
  - Skip (any item) marks it skipped.
  - "Never suggest" is only offered on suggested items (adds, swap-ins, missed items): it adds the exercise to the never-suggest list, then swaps it.
- **Preferences:**
  - `profile.avoid_muscles text[]` (valid muscle keys), `profile.never_exercises text[]`, `profile.coach_notes text` (≤ 1000 chars).
  - `GET/PUT /api/preferences`. The existing profile PUT/PATCH stay untouched.
  - Effects:
    - `gym_suggestions` skips avoided muscles and never-suggest exercises.
    - `muscle_map` marks avoided muscles `left_out: true`, excludes them from `trained_count` and from the denominator (`total` field), and gives them no suggestion.
    - The coach turn context lists the preferences.
- **Goals:**
  - `goals.exercise text null`; the coach's `save_goal` gets an optional `exercise`.
  - Tying a goal to an exercise: an explicit `exercise` match, else the exercise name without its parenthetical found in the goal text, else that name's first word (≥ 4 letters, not in the stop list: cable, machine, dumbbell, barbell, seated, standing, incline, decline, lying, single, smith) found in the goal text. All case-insensitive.
- **Weights:** dumbbell convention via `profile.dumbbell_weights` (shared `_dumbbell_weight`), rounding via `_round_down`, new-exercise estimate via `_pick`.
- **UI:** Night Shift, phone first for `/plan` (375 px, no overflow), reduced motion respected, no guilt wording.

## Review Focus

1. **A routine whose latest workout has exercises with no library entry or no muscle mapping:** they stay in the plan with a progression row, never crash, and never take part in swaps or day muscles. → Task 2 test.
2. **Preferences changed while a plan is open:** the next GET rebuilds and drops a now-avoided add. → Task 3 test.
3. **Two tabs acting on the same plan** (swap in one, skip in the other): the actions apply to the stored plan by item id, not by a stale index. → Task 3 test (two actions in a row by id).
4. **No gym history at all:** the day list is empty except "missed", which shows a friendly empty state; nothing crashes. → Task 2 test + Task 4.
5. **Goal fuzzy matching:** "Bench 100 kg" ties to "Bench Press (Barbell)" but not to "Incline Bench Press (Dumbbell)"; "Get better at cable stuff" ties to nothing. → Task 2 test.

---

### Task 1: Preferences, goal links and their effects

**Files:**
- Create: `supabase/migrations/20261027000003_planner.sql`, `lockedin/routes/preferences.py`, `tests/test_preferences.py`
- Modify:
  - `lockedin/app.py`
  - `lockedin/focus/suggest.py` (preferences filter; make `pick`, `dumbbell_weight`, `round_down` public aliases)
  - `lockedin/focus/musclemap.py`
  - `lockedin/coach/prompt.py`, `lockedin/coach/tools.py`
  - `tests/test_schema.py` (new table)

**Interfaces (produces):**
- **Migration:**
  - profile columns `avoid_muscles text[] not null default '{}'`, `never_exercises text[] not null default '{}'`, `coach_notes text not null default '' check (length(coach_notes) <= 1000)`
  - `goals.exercise text`
  - `workout_plans (id bigint identity pk, day text null, built_on date not null, source_activity_id bigint null, prefs_hash text not null, items jsonb not null, created_at timestamptz default now(), updated_at timestamptz default now())`, with RLS and the revoke
  - `coach_read` select policy/grant on nothing new (plans stay private to the app)
- **`lockedin/focus/preferences.py`:**
  - `@dataclass Preferences(avoid_muscles: list[str], never_exercises: list[str], coach_notes: str)`
  - `load_preferences(conn) -> Preferences`
  - `prefs_hash(p) -> str`: a stable sha1 of sorted avoid + never
- **Routes:**
  - `GET /api/preferences` returns `{avoid_muscles, never_exercises, coach_notes}`.
  - `PUT /api/preferences` takes the same shape and validates it:
    - muscle keys must exist in `muscles`
    - never-suggest entries are deduped and stripped, at most 200
    - notes ≤ 1000 chars
- **Effects:**
  - `gym_suggestions(conn, now, limit)` drops low muscles in `avoid_muscles`; `pick` skips exercises in `never_exercises`.
  - `muscle_map` adds per-muscle `left_out: bool` and top-level `total`; left-out muscles get `suggestion: null` and don't count in `trained_count`.
  - `turn_context` appends lines for left-out muscles, never-suggest exercises and the notes.
  - `SYSTEM_PROMPT` gains one line: "Respect the owner's training preferences in the context: never program left-out muscles or never-suggest exercises."
  - `save_goal` accepts an optional `exercise` (string ≤ 120). The prompt says to set it when a goal is about one lift.
- **Exports:** `focus/suggest.py` exports `pick`, `dumbbell_weight`, `round_down`, `NEW_EXERCISE_FACTOR`, `TARGET_REPS`. The underscore names stay as aliases or are renamed with their callers updated.

- [ ] **Step 1: Failing tests** (`tests/test_preferences.py`):
  - **API round trip:** PUT `{"avoid_muscles": ["lower_back"], "never_exercises": [" Good Morning (Barbell) ", "Good Morning (Barbell)"], "coach_notes": "Bad lower back"}` → 200, and GET returns the deduped, stripped values.
  - **Validation:** an unknown muscle → 422; notes of 1001 chars → 422; no token → 401.
  - **Body page PUT still works:** a profile PUT leaves the preferences unchanged.
  - **Focus suggestions:** `gym_suggestions` with a fixture where `lower_back` is low and avoided → no suggestion for it. An exercise on the never-suggest list isn't picked (the next library option is).
  - **Muscle map:** `muscle_map` with `avoid_muscles=['lower_back']` → `lower_back.left_out is True`, `total == 19`, and lower back doesn't count in `trained_count` even with sets.
  - **Coach context:** `turn_context` contains "Lower back" and "Bad lower back".
  - **Coach goals:** `execute_tool("save_goal", {"action": "create", "text": "Bench 100 kg", "exercise": "Bench Press (Barbell)"})` stores `exercise`; an unknown extra field → error (unchanged behaviour).
  - **Schema:** `test_schema` includes `workout_plans`.
- [ ] **Step 2:** `.venv/bin/pytest tests/test_preferences.py` → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `.venv/bin/pytest` → all pass.
- [ ] **Step 5: Commit** `feat(prefs): training preferences, goal-to-lift links, and their effect on suggestions, map and coach`.

### Task 2: Planner engine

**Files:**
- Create: `lockedin/plan/__init__.py`, `lockedin/plan/routines.py`, `lockedin/plan/goals.py`, `lockedin/plan/build.py`, `tests/test_plan_build.py`
- Modify: `lockedin/focus/wins.py` (expose `stalled_exercises(conn, now) -> list[str]`, used by `_gym_plateaus` too)

**Interfaces:**
- **`routines.py`:**
  - `@dataclass Routine(title, activity_id, last_done: datetime, exercises: list[RoutineExercise])`
  - `@dataclass RoutineExercise(name, sets, last_sets: list[tuple[float | None, int | None]])`: the non-warm-up (kg, reps) pairs in order
  - `routines(conn, now) -> list[Routine]`: the most recent first
  - `routine(conn, now, title) -> Routine | None`
- **`goals.py`:**
  - `goal_for(exercise: str, goals: list[dict]) -> dict | None`: active goals only, using the rule in Global Constraints
  - `active_goals(conn) -> list[dict]`
- **`build.py`:**
  - Item: `PlanItem = dict` with these keys:
    - `id`: short uuid hex
    - `exercise`, `equipment`
    - `kind`: `"routine" | "swap" | "add" | "missed"`
    - `sets`, `reps` (str), `weight_kg` (float | None), `dumbbell` (`"pair" | "each" | None`)
    - `change`: `"up" | "same" | "welcome_back" | "new" | None`
    - `last`: list of `{kg, reps}`
    - `replaces` (str | None), `reason` (str | None), `goal` (str | None)
    - `estimate` (bool), `skipped` (bool), `suggested` (bool: true for swap/add/missed)
  - `build_plan(conn, now, title: str | None) -> dict`: title `None` means "missed". Returns `{day, built_on, source_activity_id, prefs_hash, comeback: bool, items: [...]}`.
  - `alternatives(conn, now, item, plan_items, prefs) -> list[str]`: exercise names for Swap, in preference order.
  - `swap_item(conn, now, plan, item_id) -> dict`: returns the plan with that item replaced by the next alternative. Keep `kind` for routine items, but set `replaces` and `suggested=True` for the new exercise. Weights come from `pick`-style rules for the new exercise.

- [ ] **Step 1: Failing tests** (`tests/test_plan_build.py`). Use `focus_helpers.add_gym` with titles and `NOW = 2026-10-26 12:00 UTC`.
  - `test_routines_from_titles`:
    - Two "Chest - Schouders - Triceps" workouts (Oct 20, Oct 24) and one "Rug - Bicep" (Oct 21) → `[t.title for t in routines]` is `["Chest - Schouders - Triceps", "Rug - Bicep"]`, and the chest routine's exercises come from Oct 24 in order, with set counts that exclude warm-ups.
    - A title last used 70 days ago is excluded.
  - `test_progression_up_and_same`:
    - Bench 3 × 12 @ 80 → `change == "up"`, `weight_kg == 82.5`.
    - Bench 80×12, 80×10 → `"same"`, 80.
    - Dumbbell incline logged as pair 60 × 12 ×3 → 64 (pair, +4).
    - Lateral raise logged `each` (profile `dumbbell_weights='each'`) 12 kg ×12 → 14.
    - Bodyweight Pull Up with kg None, 12 reps ×3 → weight None, `reps == "13"` (+1 rep), `"up"`.
    - Triceps Dip (bodyweight tag) logged 10 kg ×12 ×3 → 12.5.
  - `test_unmapped_exercise_stays_without_crashing`: "Mystery Machine" in the routine → an item with `kind "routine"` and a progression row; it's not a swap candidate.
  - `test_variety_swap_on_stalled_exercise`:
    - A plateau fixture (≥ 4 recent sessions not beating 2 earlier ones) on "Overhead Press (Dumbbell)" → exactly one item with `kind "swap"`, `replaces == "Overhead Press (Dumbbell)"`, the same primary muscle (front_delt), and not in the routine.
    - With an active goal "Overhead press 30 kg each" → no swap.
  - `test_adds_for_low_day_muscles`: a chest routine (bench + incline + OHP), with rear delts low → an add for `rear_delt` in the extra block (`kind "add"`). At most 2 adds. No add for an avoided muscle (avoid `rear_delt` → none for it).
  - `test_day_muscles_secondary_not_expanded`: a back routine with a row (rear_delt secondary) and low side delts → no side-delt add.
  - `test_never_suggest_is_respected`: never `["Face Pull"]` → the rear-delt add is not Face Pull.
  - `test_comeback_holds_weights`: last session 12 days ago with 3 × 12 → `change == "welcome_back"`, the same weight, no adds or swaps, `comeback True`; `build_plan(..., None)` raises `ValueError("missed plan hidden during a comeback")`.
  - `test_missed_plan`: `build_plan(conn, NOW, None)` → ≤ 5 items, `kind "missed"`, `suggested True`, none for avoided muscles.
  - `test_goal_matching`:
    - `goal_for("Bench Press (Barbell)", [{"text": "Bench 100 kg", "exercise": None, "status": "active"}])` → that goal.
    - `goal_for("Incline Bench Press (Dumbbell)", ...)` → None.
    - "Get better at cable stuff" ties to nothing.
    - An explicit `exercise` wins.
    - Achieved or dropped goals are ignored.
  - `test_swap_item_cycles_alternatives`: swapping an add twice gives two different exercises with the same primary muscle; never-suggest ones are excluded.
  - `test_no_gym_history`: `routines(conn, NOW) == []`.
- [ ] **Step 2:** Run the tests → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `.venv/bin/pytest` → all pass.
- [ ] **Step 5: Commit** `feat(plan): routines from Hevy titles, progression, variety swap and adds`.

### Task 3: Plan API and persistence

**Files:**
- Create: `lockedin/routes/plan.py`, `tests/test_routes_plan.py`
- Modify: `lockedin/app.py`

**Interfaces (all owner-only):**
- `GET /api/plan/days` returns:
  ```
  {"days": [{"title", "last_done", "exercise_count"}],
   "missed_available": bool,
   "comeback": bool,
   "goals": [{"id", "text", "target"}]}
  ```
- `GET /api/plan?day=<title>` (omit for "missed"):
  - Returns the current plan if it's fresh, else builds, stores and returns a new one: `{id, day, built_on, comeback, items}`.
  - 404 `"No routine called …"` for an unknown title.
  - 409 `"Hidden during a comeback"` for "missed" during a comeback.
- `POST /api/plan/new?day=` always rebuilds.
- `POST /api/plan/{id}/items/{item_id}/swap`, `/skip` (toggles) and `/never`:
  - `never` is 400 on non-suggested items.
  - Each returns the updated plan. Unknown id or item → 404.
- `GET /api/goals/active` returns the active goals for the Overview card (`[{id, text, target}]`).

- [ ] **Step 1: Failing tests:**
  - `GET` builds once, then returns the same `id` on a second GET.
  - A new day (inject a clock one day later) gives a new `id`.
  - Importing a newer workout with the same title gives a new `id`.
  - Changing preferences gives a new `id`, and the now-avoided add is gone.
  - Swap by item id changes that item only. A skip then a swap on another item, both by id, both apply.
  - `never` on a routine item → 400. On an add it adds to `never_exercises` and replaces the item.
  - An unknown day → 404. "missed" during a comeback → 409.
  - `days` lists the routines with `last_done`. `goals/active` lists active goals only.
  - Every route without a token → 401.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implement. Store plans in `workout_plans`; mutations update `items` and `updated_at` in one transaction (`select … for update`).
- [ ] **Step 4:** `.venv/bin/pytest` → pass.
- [ ] **Step 5: Commit** `feat(plan): plan API with saved, self-refreshing plans`.

### Task 4: Planner UI, Overview cards, left-out muscles

**Files:**
- Create: `web/src/pages/Plan.tsx`, `web/src/lib/plan.ts` (types + `itemLine(item, dumbbellConvention)` + `changeLabel`), `web/src/lib/plan.test.ts`, `web/src/pages/Plan.test.tsx`
- Modify:
  - `web/src/App.tsx` (routes `plan`)
  - `web/src/pages/Overview.tsx` ("Going to the gym?" card at the top, "Your goals" card)
  - `web/src/pages/Muscles.tsx` (Plan a workout button; left-out style, legend entry, `total`)
  - `web/src/components/BodyFigure.tsx` (`--muscle-out` hatched-neutral fill for `left_out`)
  - `web/src/lib/types.ts`, `web/src/styles.css`

**Behaviour:**
- **`/plan`:**
  - Shows the day cards (Hevy titles as written, with last done) plus "Just what I've missed" (hidden during a comeback), and ⚙ Preferences.
  - Tapping a day loads `GET /api/plan?day=`.
- **A plan:**
  - Header: the title, "Welcome back" if it's a comeback, and a **New plan** button.
  - The items in routine order, with the swap item inline. Then "Extra, if you have time" with the adds.
  - Each item shows:
    - the name
    - `sets × reps`, and the weight via the focus-card convention ("60 kg total (30 kg each)")
    - its change label: "Up +2.5 kg", "Same weight, aim for one more rep", "Welcome back: same as last time", "New · start light"
    - "last: 80×8 · 80×8 · 77.5×7"
    - the reason, and "Goal: …"
    - **Swap**, plus ⋯ with **Skip for today** and, on suggested items only, **Don't suggest this again**
  - Skipped items are greyed out and their ⋯ reads "Undo skip". The ⋯ menu is keyboard-operable (button + menu with Escape).
- **Preferences sheet:**
  - Muscle chips toggle `avoid_muscles`.
  - A never-suggest list with "Allow again".
  - A notes textarea.
  - A Save button: `PUT /api/preferences`, then reload the plan.
- **Overview:** the "Going to the gym?" card (button → `/plan`) and the "Your goals" card (active goals and targets, link to `/coach`; with none, the one-line text from the spec).
- **Muscles page:** left-out muscles use the `--muscle-out` style; the legend gets "Left out"; the panel says "Left out in your preferences"; the chips exclude them; the counter shows `trained_count / total`.

- [ ] **Step 1: Failing tests:**
  - `plan.test.ts`: `changeLabel` for each change, and `itemLine` for pair, each and barbell.
  - `Plan.test.tsx` (jsdom, apiFetch mocked):
    - The day list renders titles.
    - Opening a day shows items and an "Extra, if you have time" block containing the add.
    - The ⋯ on a routine item has no "Don't suggest this again", but the one on an add does.
    - Clicking Swap calls the swap endpoint with that item's id.
- [ ] **Step 2:** FAIL → implement → `npx vitest run && npm run build` pass.
- [ ] **Step 3: Playwright** on the local stack with real data, at 375 px and 1440 px:
  - Overview card → `/plan`.
  - The routine titles appear.
  - Open "Chest - Schouders - Triceps": the items show "last:" rows. Swap changes an item. Skip greys it out.
  - Preferences: toggle lower back, Save. The Muscles page shows lower back as left out, with the counter `/ 19`.
  - No console errors, no overflow. Reduced motion respected.
  - Look at the screenshots.
- [ ] **Step 4: Commit** `feat(web): workout planner, preferences, gym and goals cards`.

### Task 5: Docs and wrap-up

- [ ] README: a "Workout planner" section (how routines are learned, what the changes mean, preferences and where they apply, goals) and the deploy order (`supabase db push` then `git push`).
- [ ] Run the full pytest, vitest and build, then commit `docs: workout planner`.
