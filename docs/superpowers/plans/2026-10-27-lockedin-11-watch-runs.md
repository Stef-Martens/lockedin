# Planned runs and swims on the Apple Watch: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Planned runs carry their full structure (written by the coach). A small iPhone app lists the coming runs and swims, and one tap on Apple's sheet puts each on the watch.

**Architecture:**
- **Steps.** A run's steps live in `agenda_items.targets.steps` (jsonb, no migration). They're validated by pydantic models in a new `lockedin/agenda/steps.py`, which also derives the summary targets and the one-line summary.
- **The feed.** A new read-only `GET /api/watch/runs` (its own `WATCH_TOKEN`) turns the coming runs and swims into WorkoutKit-ready JSON.
- **The app.** An XcodeGen SwiftUI app in `ios/` maps that JSON to `CustomWorkout` / `SingleGoalWorkout` and opens `.workoutPreview`.

**Tech Stack:** FastAPI + SQLAlchemy `text()` + pydantic v2, pytest against local Supabase; React 18 + Vite + Vitest; Swift 5 / SwiftUI / WorkoutKit (iOS 17), XcodeGen, `xcrun devicectl`.

**Spec:** [docs/superpowers/specs/2026-10-27-lockedin-watch-runs-design.md](../specs/2026-10-27-lockedin-watch-runs-design.md)

## Global Constraints

- **No worktrees.** Work directly on `main`; commit per task; don't push (the owner pushes).
- **No database migration.** Steps go inside the existing `targets` jsonb.
- **Steps are for runs only.** Swims get no steps (the owner's watch is on watchOS 10).
- **Heart rate on the watch** is a bpm range from LockedIn's zones (`HR_ZONE_STARTS`, `hr_zone_bounds`, `max_hr_at`). Zone 1's low end is 60 % of max HR, never 0. The watch's own zones are never used.
- **With steps, the summary targets** (`distance_m`, `duration_s`, `pace_low/high`, `hr_zone`) are always recomputed from the steps; whatever is sent for them is ignored.
- **`WATCH_TOKEN`** is optional in config (empty when unset). A watch token shorter than 16 characters must never authenticate (`MIN_SYNC_TOKEN_LEN`). It unlocks only `GET /api/watch/runs`.
- **iOS app:** deployment target iOS 17.0. Bundle id `be.stefmartens.lockedin.watch`, display name "LockedIn". No watch target, no `WorkoutScheduler`.
- **Xcode:** build with `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` (`xcode-select` points at the Command Line Tools).
- **The team ID** comes from `LOCKEDIN_TEAM_ID` or the git-ignored `ios/.team-id`, and is never committed. The owner's is `6UA7G6RXHJ` (Personal Team).
- **Copy:** plain words, the owner's units (minutes, km, m:ss per km, m:ss per 100 m).

## Review Focus

1. **The coach changes a stepped run's pace** by sending summary targets without steps. The steps stay, the summary is re-derived, and nothing is silently lost (Task 2 test).
2. **An empty or short `WATCH_TOKEN`** with a bearer like `Bearer ` or a 15-character string must get 401. The watch token must also be refused on every other route (Task 5 tests).
3. **The owner has no known max HR.** A zone target becomes no alert on the watch, never a crash or a 0 bpm range (Task 5 test).
4. **A run that clashes with time off, or is already done,** is left out of the feed (Task 5 test).
5. **A run saved before this change** (targets without steps) still loads, edits and feeds exactly as before (Task 2 and 5 tests).

---

### Task 1: The step model, derived summary and one-line summary

**Files:**
- Create: `lockedin/agenda/steps.py`
- Modify: `lockedin/agenda/store.py` (the `Targets` model, `ItemIn._fits_sport`)
- Test: `tests/test_run_steps.py`

**Interfaces:**
- Produces, in `lockedin/agenda/steps.py`:
  - pydantic models (all `extra="forbid"`):
    - `StepGoal(time_s: int|None 30..10800, distance_m: int|None 50..50000, open: bool|None)`: exactly one set (`open` must be `True` when used).
    - `StepTarget(pace_low: int|None 150..720, pace_high: int|None 150..720, hr_zone: int|None 1..5)`: pace needs both ends, with low ≤ high; pace and zone can't both be set; it can't be empty.
    - `Step(goal: StepGoal, target: StepTarget|None = None)`.
    - `BlockStep(Step)` adds `kind: Literal["work", "recovery"]`.
    - `Block(repeat: int 1..20, steps: list[BlockStep] 1..10 items)`.
    - `RunSteps(warmup: Step|None = None, blocks: list[Block] 1..10 items, cooldown: Step|None = None)`.
  - `derive(steps: RunSteps) -> dict`. Keys `distance_m`, `duration_s`, `pace_low`, `pace_high`, `hr_zone`, each an int or `None`. Each key is left `None` when it falls outside the `Targets` field range:
    - `duration_s`: the total, when every goal (repeats expanded) is a time.
    - `distance_m`: the total, when every goal is a distance.
    - `pace_low` / `pace_high`: the min and max across work steps with a pace.
    - `hr_zone`: the work steps' shared zone, when every work step has the same one.
  - `expand(steps: dict) -> list[dict]`: the steps in run order with repeats unrolled. Each is `{"kind": "warmup"|"work"|"recovery"|"cooldown", "goal": {...}, "target": {...}|None, "repeated": bool}`, where `repeated` is true inside a block with `repeat >= 2`.
  - `summary_line(sport: str, targets: dict | None) -> str | None`.
- Produces, in `store.py`:
  - `Targets.steps: RunSteps | None = None`.
  - A `Targets` after-validator: when `steps` is set, it overwrites the five summary fields with `derive(steps)`.
  - `ItemIn._fits_sport` raises "Steps are for runs only." when `targets.steps` is set on a non-run.

- [ ] **Step 1: Write the failing tests** in `tests/test_run_steps.py`: pure model and function tests, no DB. `TEMPO` is the spec's example:

```python
TEMPO = {"warmup": {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
         "blocks": [{"repeat": 4, "steps": [
             {"kind": "work", "goal": {"time_s": 300}, "target": {"pace_low": 330, "pace_high": 350}},
             {"kind": "recovery", "goal": {"time_s": 120}}]}],
         "cooldown": {"goal": {"open": True}}}

def test_summary_line_of_steps():
    assert summary_line("run", {"steps": TEMPO}) == "10' warm-up Z2 · 4 × (5' @ 5:30–5:50, 2' jog) · cool-down"

def test_summary_line_without_steps():
    assert summary_line("run", {"distance_m": 8000, "pace_low": 330, "pace_high": 350, "hr_zone": 2}) == "8 km @ 5:30–5:50 Z2"
    assert summary_line("run", {"duration_s": 2700, "hr_zone": 2}) == "45' Z2"
    assert summary_line("swim", {"distance_m": 1500, "pace_low": 120, "pace_high": 120}) == "1500 m @ 2:00/100 m"
    assert summary_line("swim", {"distance_m": 1500, "pace_low": 115, "pace_high": 125}) == "1500 m @ 1:55–2:05/100 m"
    assert summary_line("run", None) is None and summary_line("run", {}) is None

def test_time_and_distance_words():
    one = lambda goal: {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": goal}]}]}
    assert summary_line("run", {"steps": one({"time_s": 90})}) == "1'30\""
    assert summary_line("run", {"steps": one({"time_s": 45})}) == "45\""
    assert summary_line("run", {"steps": one({"distance_m": 400})}) == "400 m"
    assert summary_line("run", {"steps": one({"distance_m": 1500})}) == "1.5 km"
    assert summary_line("run", {"steps": one({"distance_m": 1000})}) == "1 km"

def test_derive_tempo():
    t = Targets(steps=TEMPO, distance_m=5000, pace_low=200, pace_high=200)  # sent summary is ignored
    assert (t.duration_s, t.distance_m, t.pace_low, t.pace_high, t.hr_zone) == (None, None, 330, 350, None)

def test_derive_all_time_and_shared_zone():
    steps = {"blocks": [{"repeat": 3, "steps": [{"kind": "work", "goal": {"time_s": 600}, "target": {"hr_zone": 4}},
                                                {"kind": "recovery", "goal": {"time_s": 120}}]}]}
    t = Targets(steps=steps)
    assert (t.duration_s, t.hr_zone, t.pace_low) == (2160, 4, None)

def test_expand_unrolls_repeats():
    kinds = [s["kind"] for s in expand(TEMPO)]
    assert kinds == ["warmup"] + ["work", "recovery"] * 4 + ["cooldown"]
    assert expand(TEMPO)[1]["repeated"] and not expand(TEMPO)[0]["repeated"]

@pytest.mark.parametrize("bad", [
    {"blocks": []},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60, "distance_m": 400}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 330}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 360, "pace_high": 330}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 330, "pace_high": 350, "hr_zone": 3}}]}]},
    {"blocks": [{"repeat": 21, "steps": [{"kind": "work", "goal": {"time_s": 60}}]}]},
    {"blocks": [{"repeat": 1, "steps": [{"kind": "work", "goal": {"time_s": 60}, "target": {"pace_low": 100, "pace_high": 120}}]}]},
])
def test_bad_steps_are_refused(bad):
    with pytest.raises(ValidationError):
        Targets(steps=bad)

def test_steps_only_on_runs():
    with pytest.raises(ValidationError, match="Steps are for runs only"):
        ItemIn(day="2026-10-28", sport="swim", title="Swim", targets={"steps": TEMPO})
```

- [ ] **Step 2: Run the tests and check they fail.** Run: `.venv/bin/python -m pytest tests/test_run_steps.py -q`. Expected: an ImportError (no `lockedin.agenda.steps`).

- [ ] **Step 3: Implement `lockedin/agenda/steps.py` and the `Targets` / `ItemIn` changes.** Format a pace with `formatDuration`-style m:ss (reuse a helper from `lockedin/agenda/actual.py` or `zwo.py` if one exists; otherwise a local `_clock`).
  - **The one-line summary:**
    - warm-up and cool-down read "<goal> warm-up <target>" and "<goal> cool-down <target>", with empty parts dropped.
    - a work step reads "<goal> <target>"; a recovery step "<goal> jog <target>".
    - a pace target reads "@ m:ss–m:ss" (or "@ m:ss" when equal); a zone "Z<n>"; an open goal is empty.
    - a block with `repeat` ≥ 2 reads "n × (a, b)"; with 1, "a, b".
    - the parts are joined with " · ".
  - **Validation errors** are raised as `ValueError` with words the coach can act on, e.g. "A step's goal needs exactly one of time_s, distance_m or open."

- [ ] **Step 4: Run the tests and check they pass.** Run: `.venv/bin/python -m pytest tests/test_run_steps.py tests/test_agenda.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.**
```bash
git add lockedin/agenda/steps.py lockedin/agenda/store.py tests/test_run_steps.py
git commit -m "feat(agenda): runs carry steps; summary targets and a one-line summary come from them"
```

### Task 2: Saving and editing runs with steps

**Files:**
- Modify: `lockedin/agenda/store.py` (`update`, `_out`)
- Test: `tests/test_run_steps_store.py`

**Interfaces:**
- Consumes: `Targets.steps`, `summary_line` (Task 1).
- Produces: every item dict from `_out` gains `"plan_line": str | None`. It's `summary_line(sport, targets)` when the item is a run with `targets.steps`, else `None`. Web and detail read it.

- [ ] **Step 1: Write the failing tests** (API level, using the `client`, `clean_db` and `clock` patterns from `tests/test_agenda.py`):
  - `test_create_run_with_steps`: POST a run with `targets={"steps": TEMPO}`. The response's `targets.steps` round-trips, `targets.pace_low == 330`, and `plan_line == "10' warm-up Z2 · 4 × (5' @ 5:30–5:50, 2' jog) · cool-down"`.
  - `test_patch_without_steps_keeps_them`: PATCH `{"targets": {"pace_low": 300, "pace_high": 310}}`. The steps are unchanged and `pace_low` is still 330 (re-derived).
  - `test_patch_title_keeps_steps`: PATCH `{"title": "Tempo"}`. The steps are unchanged.
  - `test_steps_null_removes_them`: PATCH `{"targets": {"steps": None, "distance_m": 8000}}`. Then `"steps" not in targets`, `targets == {"distance_m": 8000}` and `plan_line is None`.
  - `test_targets_null_clears_steps`: PATCH `{"targets": None}`. Then `targets is None`.
  - `test_sport_change_refused_while_steps`: PATCH `{"sport": "swim"}` returns 422 with "Steps are for runs only".
  - `test_old_run_without_steps_unchanged`: a run saved with `{"distance_m": 8000, "pace_low": 330, "pace_high": 350}`. It loads with the same targets and `plan_line is None`, and a title PATCH leaves the targets alone.

- [ ] **Step 2: Run the tests and check they fail.** Run: `.venv/bin/python -m pytest tests/test_run_steps_store.py -q`. Expected: FAIL. `test_patch_without_steps_keeps_them` loses the steps, and there's no `plan_line` key.

- [ ] **Step 3: Implement.**
  - In `update`, after `changes = patch.model_dump(exclude_unset=True)`: when `changes.get("targets")` is a dict without a `"steps"` key and the row's targets have steps, copy the row's steps into it before building `merged`. An explicit `"steps": None` stays `None` and removes them.
  - In `_out`, add `plan_line`.

- [ ] **Step 4: Run the tests and check they pass.** Run: `.venv/bin/python -m pytest tests/test_run_steps_store.py tests/test_agenda.py tests/test_agenda_polish.py tests/test_session_detail.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.**
```bash
git add lockedin/agenda/store.py tests/test_run_steps_store.py
git commit -m "feat(agenda): edits keep a run's steps; steps: null removes them; items carry plan_line"
```

### Task 3: The coach writes steps

**Files:**
- Modify: `lockedin/coach/tools.py` (`AGENDA_CHANGE.targets`, the `agenda_items` schema text), `lockedin/coach/prompt.py` (the Agenda paragraph)
- Test: `tests/test_coach_agenda.py` (add tests)

**Interfaces:**
- Consumes: the `RunSteps` JSON shape (Task 1); the store behaviour (Task 2).

- [ ] **Step 1: Write the failing tests:**
  - `test_agenda_tool_schema_has_steps`: `AGENDA_CHANGE["properties"]["targets"]["properties"]["steps"]` exists. Its `blocks.items.properties.steps.items.properties.kind.enum == ["work", "recovery"]`, and `goal` has `time_s`, `distance_m` and `open`.
  - `test_coach_saves_run_with_steps`: through the same tool-run path the existing save_agenda tests use, an add with `targets={"steps": TEMPO}` stores the steps and returns `plan_line`.
  - `test_coach_bad_steps_message`: an add with a goal holding both `time_s` and `distance_m` returns the tool error containing "exactly one of time_s, distance_m or open".
  - `test_prompt_mentions_steps`: the system prompt text contains `"steps": null` and "work out the summary".

- [ ] **Step 2: Run the tests and check they fail.** Run: `.venv/bin/python -m pytest tests/test_coach_agenda.py -q`. Expected: FAIL on the four new tests.

- [ ] **Step 3: Implement.**
  - **Add the steps schema** to `AGENDA_CHANGE.targets.properties`, with descriptions. A step is "time_s, distance_m or open: true (until the owner presses next); target: pace_low+pace_high s/km or hr_zone, not both".
  - **Update the `targets` description:**
    - Runs with structure (intervals, tempo blocks, progression) get `steps`; an easy run with one target doesn't.
    - With steps, the server works out the summary targets.
    - To change a stepped run's pace, change the steps; `"steps": null` makes it a plain run.
  - **The schema text for `agenda_items`** mentions `targets.steps`.
  - **The prompt.** Replace "Give runs and swims targets (…)" with words to this effect:
    - Give runs and swims targets.
    - Give structured runs steps (warm-up, repeat blocks of work and recovery, cool-down); the server will work out the summary from them, and they go to the owner's Apple Watch.
    - To make a stepped run plain, send `"steps": null`.
    - Swims get no steps (the owner's watch can't take them); put the set in the note.

- [ ] **Step 4: Run the tests and check they pass.** Run: `.venv/bin/python -m pytest tests/test_coach_agenda.py tests/test_coach_tools.py tests/test_coach_loop.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.**
```bash
git add lockedin/coach/tools.py lockedin/coach/prompt.py tests/test_coach_agenda.py
git commit -m "feat(coach): plans structured runs as steps for the watch"
```

### Task 4: Fitness ahead counts a stepped run's real load

**Files:**
- Modify: `lockedin/forecast/ahead.py` (`planned_load`)
- Test: `tests/test_planned_tss.py` (add tests)

**Interfaces:**
- Consumes: `expand(steps)` (Task 1); `ZONE_IF`, `UNMEASURED_IF`.

- [ ] **Step 1: Write the failing tests:**
  - `test_stepped_run_uses_step_time`: with an all-time-goal run of 10' Z2 + 3 × (10' Z4, 2' recovery) + 10' Z2, `planned_load == sum(s/3600 × IF² × 100)`. The IFs: Z2 → `ZONE_IF[2]`, Z4 → `ZONE_IF[4]`, recovery with no target → `ZONE_IF[1]`.
  - `test_tempo_harder_than_easy_same_length`: 4 × (5' at pace, 2' jog) plus 10' warm-up and 10' cool-down (no targets) loads more than a plain run with `duration_s` equal to that total time and no zone.
  - `test_distance_steps_use_their_pace`: a 5 × (1000 m @ 4:00–4:10) block counts 5 × 245 s at the work-step IF.
  - `test_open_steps_are_skipped`: an open cool-down adds nothing.

- [ ] **Step 2: Run the tests and check they fail.** Run: `.venv/bin/python -m pytest tests/test_planned_tss.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** When `targets.steps` exists, `planned_load` sums over `expand(steps)`:
  - **Time:**
    - a time goal → `time_s`.
    - a distance goal → distance / 1000 × the step's mean pace, or the run's summary pace when the step has none, or it's skipped.
    - an open goal → skipped.
  - **Intensity:**
    - a step with `hr_zone` → `ZONE_IF[zone]`.
    - a `work` step with `repeated` and a pace → `ZONE_IF[4]` *(ruling: repeats at pace are hard work; there's no threshold pace to compare with)*.
    - a `recovery` step → `ZONE_IF[1]`.
    - anything else → `UNMEASURED_IF`.
  - **Without steps:** unchanged.

- [ ] **Step 4: Run the tests and check they pass.** Run: `.venv/bin/python -m pytest tests/test_planned_tss.py tests/test_forecast.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.**
```bash
git add lockedin/forecast/ahead.py tests/test_planned_tss.py
git commit -m "feat(forecast): fitness ahead counts a stepped run's time and intensity"
```

### Task 5: The watch feed

**Files:**
- Create: `lockedin/watch.py`, `lockedin/routes/watch.py`, `ios/Tests/feed-sample.json` (written by this task's test fixture)
- Modify: `lockedin/config.py` (`watch_token`), `lockedin/auth.py` (`require_owner_or_watch`), `lockedin/app.py` (include the router), `tests/conftest.py` (`WATCH_TOKEN`), `.env.example`
- Test: `tests/test_watch_feed.py`

**Interfaces:**
- Consumes: `items_between` (with `done` and `clash`), `summary_line`, `expand`, `hr_zone_bounds`, `max_hr_at`.
- Produces:
  - `Settings.watch_token: str = ""`, read from `WATCH_TOKEN`.
  - `require_owner_or_watch(authorization) -> Literal["owner", "watch"]`.
  - `feed(conn: Connection, now: datetime) -> dict`.
  - `GET /api/watch/runs` returns `feed(...)`.
- **The JSON contract** (the iOS app in Task 7 decodes exactly this):

```json
{"today": "2026-10-27",
 "items": [
  {"id": 1, "day": "2026-10-27", "sport": "run", "title": "Tempo", "optional": false, "note": null,
   "summary": "10' warm-up Z2 · 4 × (5' @ 5:30–5:50, 2' jog) · cool-down",
   "workout": {"kind": "run", "display_name": "Tempo", "location": "outdoor",
     "warmup": {"goal": {"type": "time", "seconds": 600}, "alert": {"type": "heart_rate", "min_bpm": 137, "max_bpm": 156}},
     "blocks": [{"iterations": 4, "steps": [
        {"purpose": "work", "goal": {"type": "time", "seconds": 300}, "alert": {"type": "speed", "min_mps": 2.857, "max_mps": 3.03}},
        {"purpose": "recovery", "goal": {"type": "time", "seconds": 120}, "alert": null}]}],
     "cooldown": {"goal": {"type": "open"}, "alert": null}}},
  {"id": 2, "day": "2026-10-28", "sport": "swim", "title": "Swim", "optional": false, "note": "4 × 100 m, 30 s rest",
   "summary": "1500 m @ 2:00/100 m",
   "workout": {"kind": "swim", "display_name": "Swim", "location": "pool", "goal": {"type": "distance", "meters": 1500}}}
 ]}
```
  - Goals: `{"type": "time", "seconds"}`, `{"type": "distance", "meters"}` or `{"type": "open"}`.
  - Alerts: `{"type": "speed", "min_mps", "max_mps"}` (min = 1000 / pace_high, max = 1000 / pace_low, 3 decimals), `{"type": "heart_rate", "min_bpm", "max_bpm"}`, or `null`.
  - A run without steps is one block (`iterations: 1`) of one work step:
    - goal: `distance_m`, else `duration_s`, else open.
    - alert: its pace, else its zone, else `null`.
  - A swim's goal is `distance_m`, else `duration_s`, else open.

- [ ] **Step 1: Write the failing tests** in `tests/test_watch_feed.py`. Set the clock to `NOW = 2026-10-27 08:00 UTC`, set `profile.max_hr_override = 190`, and set `WATCH_TOKEN` in conftest to `"watch-test-token-0123456789"`.
  - `test_feed_contract`: seed the tempo run (today) and the swim (tomorrow) above. `GET /api/watch/runs` with the watch token equals the contents of `ios/Tests/feed-sample.json`, ids aside. The test writes the file when `UPDATE_FEED_SAMPLE=1` and compares otherwise; commit the file it writes. With max HR 190, zone 2 is (round(190 × .72), round(190 × .82)) = (137, 156), as in the contract above.
  - `test_zone_one_starts_at_60_percent`: a zone 1 step gives `min_bpm == round(190 × .60)`.
  - `test_no_max_hr_drops_hr_alert`: with no max HR (no override, no streams, no date of birth), a zone step's alert is `null` and the feed still returns 200.
  - `test_window_and_filters`: the feed leaves out:
    - a run yesterday
    - a run 8 days ahead
    - a done run (an activity on the day ticks it)
    - a run on a day with a `run` time-off restriction
    - gym and bike items

    It keeps an optional run, with `optional: true`. The day order is kept.
  - `test_run_without_steps`: `{"distance_m": 8000, "pace_low": 330, "pace_high": 350}` gives one block, `iterations` 1, a distance goal of 8000 and a speed alert.
  - `test_auth`:
    - the owner JWT gets 200; the watch token gets 200.
    - no header gets 401; the sync token gets 401.
    - the watch token on `GET /api/agenda` gets 401.
  - `test_short_or_empty_watch_token_never_authenticates`: monkeypatch `get_settings().watch_token` to `""` and then to `"short"` (clear the `lru_cache` or override the settings the way `tests/test_auth_hardening.py` does). `Bearer ` and `Bearer short` both get 401.

- [ ] **Step 2: Run the tests and check they fail.** Run: `.venv/bin/python -m pytest tests/test_watch_feed.py -q`. Expected: FAIL (404, no route).

- [ ] **Step 3: Implement.**
  - **`require_owner_or_watch`** mirrors `require_owner_or_sync`, including the `len >= MIN_SYNC_TOKEN_LEN` check and `hmac.compare_digest`.
  - **`feed`** uses `items_between(conn, now, today, today + 7 days)`, keeps runs and swims that aren't done and have no `clash`, and builds each run's workout from `targets.steps`. Warm-up, blocks and cool-down map one to one, with repeats kept as `iterations`, not unrolled.
  - **Heart-rate alerts** come from `hr_zone_bounds(max_hr_at(conn, now))`, with zone 1's low end replaced by `round(max_hr × 0.60)`.
  - **`.env.example`** gains `WATCH_TOKEN=` with a comment.

- [ ] **Step 4: Run the tests and check they pass.** Run `UPDATE_FEED_SAMPLE=1 .venv/bin/python -m pytest tests/test_watch_feed.py -q`, then `.venv/bin/python -m pytest -q`. Expected: the whole suite passes. Read `ios/Tests/feed-sample.json` and check it matches the contract's shape.

- [ ] **Step 5: Commit.**
```bash
git add lockedin/watch.py lockedin/routes/watch.py lockedin/config.py lockedin/auth.py lockedin/app.py tests/conftest.py tests/test_watch_feed.py ios/Tests/feed-sample.json .env.example
git commit -m "feat(watch): read-only feed of the coming runs and swims, ready for WorkoutKit"
```

### Task 6: Web shows the steps and keeps them

**Files:**
- Modify: `web/src/lib/agenda.ts` (types), `web/src/pages/Agenda.tsx` (item sub-line), `web/src/pages/Overview.tsx` (today line), `web/src/pages/session/PlanSection.tsx`, `web/src/pages/session/Edit.tsx`
- Test: `web/src/pages/Agenda.test.tsx`, `web/src/pages/Session.test.tsx` (add tests)

**Interfaces:**
- Consumes: `AgendaItem.plan_line` and `targets.steps` (Task 2).
- Produces:
  - `Targets` gains `steps?: RunSteps`, with `RunSteps` typed to the Task 1 shape.
  - `AgendaItem` gains `plan_line: string | null`.

- [ ] **Step 1: Write the failing tests:**
  - **Agenda:** a not-done run with `plan_line` shows it as the sub-line, in place of the note.
  - **Session page:** the plan card of a run with `plan_line` shows the line.
  - **Edit:** for a run with `targets.steps`, the form shows no Distance, Duration, Pace or zone fields. It shows the `plan_line` and "Ask the coach to change the steps." Saving a changed title sends exactly `{"title": "…"}` (no `targets` key).
  - **Edit:** for a run without steps, the target fields are still there (the existing tests keep passing).

- [ ] **Step 2: Run the tests and check they fail.** Run: `npm --prefix web test -- --run`. Expected: FAIL on the new tests.

- [ ] **Step 3: Implement.**
  - **The sub-line**, on both Agenda and Overview, becomes `item.done ? item.result : item.zwift?.summary ?? item.plan_line ?? item.note`.
  - **PlanSection** renders `item.plan_line` above the tiles when set. The tiles still show the derived summary.
  - **Edit:** `withTargets` is false when `t.steps` exists; then the summary line and the hint render instead.

- [ ] **Step 4: Run the tests and check they pass.** Run `npm --prefix web test -- --run && npm --prefix web run lint && npm --prefix web run build`. Expected: everything passes, no lint errors, and the build succeeds.

- [ ] **Step 5: Commit.**
```bash
git add web/src
git commit -m "feat(web): stepped runs show their summary; editing keeps the steps"
```

### Task 7: The iPhone app, its install command and the README

**Files:**
- Create:
  - `ios/project.yml`
  - `ios/Sources/LockedInApp.swift`, `ios/Sources/Feed.swift`, `ios/Sources/Workouts.swift`, `ios/Sources/Keychain.swift`, `ios/Sources/SessionsView.swift`, `ios/Sources/SettingsView.swift`
  - `ios/Tests/FeedTests.swift`
  - `ios/install.sh`, `ios/.gitignore`
- Modify: `Makefile` (`ios` target), `README.md` (new section "13. Runs and swims on the Apple Watch" and the env table row for `WATCH_TOKEN`)

**Interfaces:**
- Consumes: the JSON contract and `ios/Tests/feed-sample.json` (Task 5).
- Produces:
  - `struct Feed: Decodable { today: String; items: [FeedItem] }` and the nested `Decodable` types for goals, alerts and steps (`FeedItem` is `Identifiable` by `id`).
  - `enum FeedError: LocalizedError` with the cases `noConnection`, `wrongKey` (401), `server(Int)`, `badData`. `errorDescription` gives plain words.
  - `func fetchFeed(base: URL, key: String) async throws -> Feed`.
  - `func workoutPlan(for item: FeedItem) throws -> WorkoutPlan`:
    - a run → `.custom(CustomWorkout(activity: .running, location: .outdoor, displayName:, warmup:, blocks:, cooldown:))`. Speed alerts become `SpeedRangeAlert(target: min...max m/s, metric: .current)`. Heart-rate alerts become `HeartRateRangeAlert(target: min...max)` (check the exact initializer in the iOS SDK's WorkoutKit `.swiftinterface`).
    - a swim → `.goal(SingleGoalWorkout(activity: .swimming, swimmingLocation: .pool, goal:))`.

- [ ] **Step 1: Write the failing test** `ios/Tests/FeedTests.swift` (XCTest, unit test target `LockedInTests` in `project.yml`):
  - `testDecodesSample`: decodes `feed-sample.json` (bundled as a test resource). It checks 2 items, the first a run whose first block has 4 iterations.
  - `testRunPlanShape`: `workoutPlan(for:)` of the sample run gives a `.custom` workout with `blocks.count == 1`, `blocks[0].iterations == 4`, `warmup != nil` and the display name "Tempo".
  - `testSwimPlanShape`: the sample swim gives `.goal` with activity `.swimming`.

- [ ] **Step 2: Run the test and check it fails.** Run: `cd ios && xcodegen generate && DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild test -project LockedIn.xcodeproj -scheme LockedIn -destination 'platform=iOS Simulator,name=<an installed iPhone simulator>'`. List simulators with `xcrun simctl list devices available | grep iPhone`. Expected: it fails to compile (no `workoutPlan`).

- [ ] **Step 3: Implement the app.**
  - **First launch** (or the gear button) shows `SettingsView`: the LockedIn address and the watch key, saved to the Keychain.
  - **`SessionsView`:**
    - it loads on appear and refreshes on pull.
    - runs are grouped by day: "Today", "Tomorrow", else e.g. "Thu 30 Oct".
    - each row shows the title, the summary, an "Optional" tag, and for swims the note.
    - errors show in words, in a banner above the list.
  - **Tapping a row** opens `.workoutPreview(plan, isPresented:)`. When one item can't be built, an inline error shows on that row, and the rest work.
  - **`ios/install.sh`** (`set -euo pipefail`):
    - reads the team ID from `LOCKEDIN_TEAM_ID` or `ios/.team-id`, and exits with a clear message when it has neither.
    - picks the device from `IOS_DEVICE`, else the first connected physical iPhone in `xcrun devicectl list devices`.
    - runs `xcodegen generate`, then `xcodebuild build` with `-allowProvisioningUpdates -allowProvisioningDeviceRegistration DEVELOPMENT_TEAM=$TEAM -derivedDataPath ios/build`.
    - installs with `xcrun devicectl device install app` and launches with `xcrun devicectl device process launch --terminate-existing`.
    - when the launch fails with the trust error, it prints a hint about Settings → General → VPN & Device Management.
  - **`Makefile`:** `ios:` runs `./ios/install.sh`.
  - **`ios/.gitignore`:** `build/`, `*.xcodeproj`, `.team-id`.
  - **The README section:**
    - what it does
    - setting `WATCH_TOKEN` on Vercel
    - `brew install xcodegen`
    - the one-time setup: Xcode account, Developer Mode, trusting the certificate
    - `make ios` every 7 days
    - the watchOS 10 limits: one tap per run, no swim steps
    - "Later: automatic with a newer watch"

- [ ] **Step 4: Run the tests and check they pass, then build for the device.**
  - Run the Step 2 command. Expected: `** TEST SUCCEEDED **`.
  - Then run `LOCKEDIN_TEAM_ID=6UA7G6RXHJ ./ios/install.sh` with the owner's iPhone connected. Expected: `** BUILD SUCCEEDED **`, "App installed" and "Launched application".

    If no iPhone is connected, run only the `xcodebuild build` for `generic/platform=iOS` with `CODE_SIGNING_ALLOWED=NO`, and say so in the report.

- [ ] **Step 5: Commit.**
```bash
git add ios Makefile README.md
git commit -m "feat(ios): LockedIn iPhone app puts planned runs and swims on the Apple Watch"
```
