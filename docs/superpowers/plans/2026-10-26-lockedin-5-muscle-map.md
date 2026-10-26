# LockedIn Plan 5: Muscle Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Muscles page: front and back of a body that fill in lime as gym sets are logged during the week, with ride/run/swim minutes as a separate striped layer. Hovering a muscle shows that week's sets, the days, the history and its main lift.

**Architecture:**
- **Backend:** a new focus module `lockedin/focus/musclemap.py` builds the whole week in one dict. It shares the set-counting SQL with `muscle_coverage` through a new `set_credit()` helper. `GET /api/muscle-map?week=` serves it.
- **Frontend:**
  - a hand-authored SVG `BodyFigure` component (front/back, 20 muscles)
  - pure helpers in `lib/musclemap.ts`
  - a `Muscles` page with a hover panel, pinning, week arrows, chips and a list view

**Tech:** existing stack (FastAPI, SQLAlchemy Core, React + TS, Vitest, Playwright for verification).

**Spec:** `docs/superpowers/specs/2026-10-26-lockedin-muscle-map-design.md`.

## Global Constraints

- **Weeks:** Monday 00:00 to next Monday 00:00 in Europe/Brussels (`timeutil.TZ`, `week_start`), correct across DST. "Week end" = next Monday 00:00, or `now` for the current week.
- **Sets:** counted sessions only (`counted('a')`), primary = 1, secondary = ½, `set_type <> 'warmup'`, mapped via `library_muscles`. Must be the same SQL `muscle_coverage` uses.
- **Shades:**
  - 0 → level 0
  - 0 < s < low → level 1
  - low ≤ s ≤ high → level 2
  - s > high → level 3
  - If `target_low` is 0, any s > 0 is level 2 (or level 3 when s > high).
- **Cardio never adds sets.** These sports draw stripes on these muscles:
  - `bike` (`--sport-bike`): quads, glutes, hamstrings, calves
  - `run` (`--sport-run`): quads, glutes, hamstrings, calves
  - `swim` (`--sport-swim`): lats, front_delt, side_delt, rear_delt, triceps
  - Stripe opacity is `0.35 + 0.65 * min(minutes, 120) / 120`.
  - Walks are excluded (counted-session rule).
- **Earlier weeks:**
  - The main lift's 8-week window, "not lately" (no session in the 28 days before week end), "last trained" (last counted gym session before week start) and the 6-week history all measure from the selected week's end.
  - Suggestions appear only on the current week: `gym_suggestions(conn, now, limit=20)`.
- **Counter and chips are gym-only:** "N / 20 muscles trained in the gym"; the chips are headed "No gym work yet", with a sport-coloured dot when a muscle has cardio that week.
- **No guilt:** no red, no "missed" or "behind".
- **Colours:** shade tokens `--muscle-0 #2c3034`, `--muscle-1 #55682a`, `--muscle-2 #94bd48`, `--muscle-3 #c8f169`.
- **Motion:** reduced motion turns all animation off.
- **Layout:** desktop first (≥ 1200 px: two figures plus the side column in one row); no horizontal overflow at 375 px.
- **Accessibility:**
  - Every muscle shape is focusable, with an accessible name like "Quads: 0 sets this week, 46 minutes on the bike".
  - Focus shows the same details as hover.
  - A "Show as list" toggle shows the same data as a table.

## Review Focus

1. **Week boundaries across DST:** a set on Sunday 25 Oct 2026 at 23:30 Brussels (DST ended that morning) belongs to the week of 19 Oct; one on Monday 26 Oct at 00:30 belongs to the next week. → Task 1 test.
2. **A brand-new or empty database** (no gym sessions ever): every muscle grey, `first_week` null, both arrows disabled, no crash, and a friendly empty message. → Task 1 test + Task 3 Playwright.
3. **A `?week=` in the future or garbage:** a future date clamps to the current week; a malformed one gives 422 from the API, and the page falls back to the current week. → Task 1 test + Task 3.
4. **Exercises with no muscle mapping:** ignored for sets (as in coverage). They never crash the main-lift query. → Task 1 test.
5. **Hover panel at the screen edges and keyboard-only use:** the panel stays inside the viewport; Tab reaches muscles, and Escape unpins. → Task 3 Playwright.

---

### Task 1: Muscle map data and API

**Files:**
- Modify: `lockedin/focus/coverage.py` (extract `set_credit`)
- Create: `lockedin/focus/musclemap.py`
- Modify: `lockedin/routes/trends.py` (add the route)
- Test: `tests/test_muscle_map.py`

**Interfaces (produces):**
- `set_credit(conn, since: datetime, until: datetime) -> dict[str, float]`: the muscle_key → sets sum for `since < start_at <= until`, using the constraint SQL. `muscle_coverage` must use it and return exactly what it returns today; the existing coverage tests stay green unchanged.
- `CARDIO_MUSCLES: dict[str, list[str]]` as in Global Constraints.
- `muscle_map(conn, now: datetime, week: date | None) -> dict` (jsonable). `week` is any date in the week; `None` or a future date means the current week. Shape:

```
{"week_start": "2026-10-19", "is_current": false, "first_week": "2026-09-14" | null, "trained_count": 10,
 "cardio": [{"sport": "bike", "minutes": 46, "days": ["2026-10-25"]}],          # only sports with minutes > 0
 "muscles": [{                                                                    # all 20, in muscles.sort order
   "key", "name", "region", "target_low", "target_high", "sets": 8.5,
   "days": [{"date": "2026-10-20", "exercises": [{"name": "Bench Press (Barbell)", "sets": 3.0}]}],
   "history": [{"week_start": "2026-09-14", "sets": 6.0}, ... 6 items, oldest first, last = selected week],
   "last_trained": "2026-10-09" | null,          # last counted gym day hitting this muscle before week_start
   "lift": {"exercise", "first_e1rm", "latest_e1rm", "status": "trend" | "new" | "not_lately"} | null,
   "cardio": [{"sport": "bike", "minutes": 46}],  # sports from the week's cardio that use this muscle
   "suggestion": GymSuggestion | null}]}         # current week only
```

- **Main lift:**
  - It's the exercise with the most primary-role working sets for the muscle in the 8 weeks before week end; ties go to the higher best e1RM, then the name.
  - `first_e1rm` / `latest_e1rm` are the best non-warm-up e1RM in its earliest / latest session in that window.
  - `status` is:
    - `"new"` with one session
    - `"not_lately"` when the latest session is more than 28 days before week end
    - otherwise `"trend"`
  - `null` when the exercise has no e1RM values.
- **Route:** `GET /api/muscle-map?week=YYYY-MM-DD` (optional; FastAPI `date`, so a malformed value gives 422) → `muscle_map(conn, now, week)`.

- [ ] **Step 1: Write failing tests** in `tests/test_muscle_map.py`. Use `focus_helpers.add_gym` / `add_session` and `NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)` (a Monday). Seeded library: Bench Press (Barbell) is primary `mid_lower_chest`, secondary `upper_chest`, `front_delt` and `triceps`.
  - `test_counts_one_week_of_sets`: 3 normal sets plus 1 warm-up of bench on Tue 20 Oct.
    - Week 2026-10-19 gives `mid_lower_chest.sets == 3` and `triceps.sets == 1.5`.
    - `days == [{"date": "2026-10-20", "exercises": [{"name": "Bench Press (Barbell)", "sets": 3.0}]}]` for mid_lower_chest.
    - `trained_count == 4`.
  - `test_week_boundary_across_dst`:
    - A set at 2026-10-25 22:30 UTC (Sun 23:30 Brussels) is in week 19 Oct.
    - One at 2026-10-25 23:30 UTC (Mon 00:30) is in week 26 Oct.
  - `test_coverage_unchanged`: `muscle_coverage` on a fixture equals its values before the refactor. Assert concrete numbers for one muscle.
  - `test_cardio_is_a_separate_layer`:
    - A 46-min bike session on Sun 25 Oct gives `cardio == [{"sport": "bike", "minutes": 46, "days": ["2026-10-25"]}]`.
    - quads `cardio == [{"sport": "bike", "minutes": 46}]` and quads `sets == 0`; quads is not counted in `trained_count`.
    - A run with `sub_type="walking"` and a superseded bike session add nothing.
  - `test_last_trained_is_before_the_selected_week`: legs on 9 Oct gives quads `last_trained == "2026-10-09"` for week 19 Oct. For week 5 Oct it is null when nothing came earlier.
  - `test_history_six_weeks_ending_with_selected`: `len == 6`, the last `week_start` is the selected week, and the values match the sets.
  - `test_main_lift_trend_new_and_not_lately`:
    - Bench on 21 Sep (e1RM 76) and 20 Oct (e1RM 101.3) gives `{"exercise": "Bench Press (Barbell)", "first_e1rm": 76.0, "latest_e1rm": 101.3, "status": "trend"}` (approximate floats).
    - A single session gives `"new"`.
    - The latest session 30 days before week end gives `"not_lately"`.
  - `test_suggestions_only_on_current_week`:
    - With low coverage, current week: at least one muscle has a non-null `suggestion`.
    - Week 19 Oct: all null.
  - `test_empty_database`: all 20 muscles, `sets == 0`, `first_week is None`, `trained_count == 0`, `cardio == []`.
  - `test_future_week_clamps_to_current`: `week=date(2027, 1, 4)` gives `week_start == "2026-10-26"` and `is_current is True`.
  - `test_unmapped_exercise_is_ignored`: sets of "Mystery Machine" add nothing and don't crash.
  - Route tests: 200 with `?week=2026-10-21` (`week_start` "2026-10-19"); 422 with `?week=nope`; 401 without a token.
- [ ] **Step 2:** Run `.venv/bin/pytest tests/test_muscle_map.py`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `set_credit`, `musclemap.py` and the route.
- [ ] **Step 4:** Run `.venv/bin/pytest`. Expected: all pass, including the existing coverage, suggestion and focus tests.
- [ ] **Step 5: Commit** `feat(muscles): weekly muscle map data and API`.

### Task 2: Body figure and pure helpers

**Files:**
- Create: `web/src/components/BodyFigure.tsx`, `web/src/lib/musclemap.ts`
- Modify: `web/src/lib/types.ts` (MuscleMap types matching Task 1's shape)
- Test: `web/src/lib/musclemap.test.ts`, `web/src/components/BodyFigure.test.tsx`

**Interfaces:**
- **Consumes:** Task 1's JSON.
- **`lib/musclemap.ts`:**
  - `shadeLevel(sets: number, low: number, high: number): 0 | 1 | 2 | 3`, per Global Constraints.
  - `stripeOpacity(minutes: number): number`.
  - `CARDIO_COLOR: Record<"bike" | "run" | "swim", string>` (CSS var names).
  - `muscleLabel(m: MapMuscle): string`, e.g. "Quads: 0 sets this week, 46 minutes on the bike" or "Triceps: 17 sets this week".
  - `shiftWeek(weekStart: string, by: number): string`, an ISO date ± 7·by days.
- **`BodyFigure`:** `({ side: "front" | "back", muscles: MapMuscle[], focused: string | null, pinned: string | null, onHover(key | null), onPin(key) }) => JSX`.
  - Inline SVG.
  - Each muscle is a `<path data-m={key} tabIndex={0} role="button" aria-label={muscleLabel}>` (paired muscles get two paths, but only the left one is in the tab order).
  - Fill is `var(--muscle-N)`.
  - Cardio stripes use an SVG `<pattern>` per sport; when there are two sports, the pattern alternates their colours. Stripes go on an overlay copy with `pointer-events: none`.
  - Front muscles are the spec's front list; back muscles are the back list.
  - The paths must read as an anatomical figure (spec anti-goal), not the mockup's blocks.

- [ ] **Step 1: Write failing tests:**
  - `shadeLevel`:
    - `(0,4,14)→0`, `(2,4,14)→1`, `(4,4,14)→2`, `(14,4,14)→2`, `(15,4,14)→3`
    - `(1,0,8)→2`, `(9,0,8)→3`
  - `stripeOpacity`: `(0)≈0.35`, `(60)≈0.675`, `(240)=1`.
  - `muscleLabel`: both example strings.
  - `shiftWeek`: `("2026-10-26",-1)→"2026-10-19"`, and across the March DST change `("2026-03-30",-1)→"2026-03-23"`.
  - `BodyFigure` (render with `react-dom/server`):
    - The front and back views together contain each of the 20 muscle keys at least once.
    - Front has no `lats`; back has no `abs`.
    - A muscle with `sets: 0` renders with `var(--muscle-0)`.
- [ ] **Step 2:** Run `cd web && npx vitest run`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `npx vitest run && npm run build`. Expected: pass.
- [ ] **Step 5: Commit** `feat(web): anatomical body figure and muscle map helpers`.

### Task 3: Muscles page

**Files:**
- Create: `web/src/pages/Muscles.tsx`
- Modify: `web/src/App.tsx` (route `muscles`), `web/src/components/Layout.tsx` (nav item "Muscles" right after Trends; the tab bar fits at 375 px), `web/src/styles.css` (tokens `--muscle-0..3`, page styles)
- Verify: Playwright script in the scratchpad (not committed)

**Behaviour (spec Goals):**
- **Header:** "Week of 19 Oct" with ‹ › and a `?week=` URL.
  - ‹ is disabled at `first_week` or when it's null.
  - › is disabled on the current week.
  - On a 422, the page uses the current week.
- **Main row:** the front and back figures, then the side column:
  - "N / 20 muscles trained in the gym"
  - "No gym work yet" chips (with sport dots); hovering a chip highlights the muscle and clicking pins it
  - the pinned muscle's details
- **Hover panel** (fixed, follows the mouse, clamped to the viewport), with these contents:
  - name, sets with "aim low–high" and the target-band bar
  - the trained days with their exercises
  - cardio minutes per sport, with days
  - the 6-week bars
  - the main lift line (`trend`: "76 → 101.3 kg"; `new`: "101.3 kg · new"; `not_lately`: "101.3 kg · not lately")
  - when sets are 0: "last on Fri 9 Oct" or "Not in your logs yet", plus the suggestion (exercise, sets × reps, weight)
- **Legend:** grey plus three lime shades, and stripes for the sports present.
- **"Show as list" toggle:** a table with muscle, sets, aim, cardio, last trained.
- **Keyboard:** focusing a muscle shows its details in the side column; Enter or Space pins; Escape unpins.
- **Empty database:** all grey, with the note "Log a gym session in Hevy and import it to see your week fill in."

- [ ] **Step 1:** Implement the page, nav and styles.
- [ ] **Step 2:** Run `cd web && npx vitest run && npm run build`. Expected: pass.
- [ ] **Step 3: Playwright** against the local stack with real data, at 1440 px and 375 px:
  - The page renders.
  - Hovering triceps on week 19 Oct shows "17" and "aim 4–14".
  - Hovering quads shows "46′" and the bike.
  - ‹ changes the week and the URL.
  - `?week=nope` falls back to the current week.
  - Tab, Enter and Escape work.
  - The hover panel near the right edge stays on screen.
  - No console errors, no horizontal overflow.
  - Reduced motion: no running animations.
  - Look at the screenshots: the figure must read as a body.
- [ ] **Step 4: Commit** `feat(web): Muscles page with weekly body map`.

### Task 4: Docs and wrap-up

- [ ] README section 6: a "Muscles" paragraph (what the colours and stripes mean, gym-only counter, hover/pin, earlier weeks).
- [ ] Run the full `pytest`, `vitest` and build, then commit `docs: muscle map`.
