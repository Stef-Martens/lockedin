# LockedIn: Muscle map

**Status:** design approved in conversation on 2026-10-26.
**Builds on:** the main spec (`2026-10-25-lockedin-design.md`), the focus engine (Plan 2), Night Shift UI (Plan 3).

## Why

The owner wants to glance at one picture and see what they trained this week, and what they didn't. In their words: "just what i did that week, like see what i trained about my body and what not." The existing Muscle coverage list on Trends → Gym has the numbers, but it's a 28-day average in a list, not this week on a body.

They'll use it almost only on desktop, so hover is the main interaction. The phone just has to work.

## Goals

- A **Muscles** page with a front and a back view of a body, side by side.
- **Monday start:** every muscle is grey at the start of the week (Monday 00:00, Europe/Brussels) and fills in as gym sets are logged that week.
- **Shading:** the 20 muscles the app already tracks (`muscles` table) fill in three lime shades of the same hue, measured against each muscle's weekly target (`target_low`/`target_high`):
  - **Not trained:** 0 sets (grey).
  - **A little:** more than 0 but below `target_low`.
  - **On target:** from `target_low` up to and including `target_high`.
  - **Lots:** above `target_high`. A positive shade, not a warning.
  - For muscles whose `target_low` is 0 (forearms, abductors), any set counts as on target.
- **Sets** are counted exactly like `muscle_coverage`:
  - counted sessions only
  - primary muscle = 1 set, secondary = ½
  - warm-ups excluded
  - exercises map to muscles through `library_muscles`
  - The difference: it sums one calendar week instead of averaging 28 days.
- **Cardio is its own layer and never counts as sets.** Counted sessions draw diagonal stripes over the muscles they use:
  - **Bike** (blue, `--sport-bike`): quads, glutes, hamstrings, calves.
  - **Run** (orange, `--sport-run`): quads, glutes, hamstrings, calves.
  - **Swim** (teal, `--sport-swim`): lats, front delts, side delts, rear delts, triceps.
  - Stripes get stronger with the week's minutes in that sport, at full strength from 120 minutes.
  - If two sports hit the same muscle in a week, the stripes alternate their colours.
  - Walks don't count (same counted-session rule as everywhere).
  - Owner's reason: rides do train legs, but if they counted as sets the focus suggestions would stop asking for leg work after a week of Zwift.
- **Hovering a muscle** shows a panel with:
  - the muscle's name, and its sets this week against "aim low–high", with a small bar showing the target band
  - the days it was trained this week and the exercises that hit it
  - for muscles under a cardio layer: minutes per sport this week and on which days
  - its weekly sets for the last 6 weeks, ending with the selected week, as small bars with the selected week highlighted
  - its **main lift** and how it moved: the exercise with the most primary-role working sets for this muscle in the last 8 weeks, and its best estimated 1RM in the earliest session in that window vs. the latest session (e.g. "Bench Press (Barbell) 76 → 101.3 kg")
    - Only one session in the window: show the latest value with "new".
    - Not done in the last 4 weeks: show the latest value with "not lately".
    - No e1RM (bodyweight, timed): no strength line.
  - If not trained this week: when it was last trained ("last on Fri 9 Oct"), or "Not in your logs yet". Plus the focus engine's suggestion for that muscle when there is one (exercise and weight, from `gym_suggestions`).
- **Side column:**
  - "N / 20 muscles trained" this week.
  - A "Not trained yet" list as chips. Hovering a chip highlights that muscle on the body; clicking it pins its details.
- **Week arrows** (‹ ›) step back through earlier weeks, as far back as the first week with any data. › is disabled on the current week. The URL keeps the week (`/muscles?week=2026-10-19`) so it can be linked and survives a reload.
- **Click** pins a muscle's details in the side column (the hover panel follows the mouse); clicking it again or pressing Escape unpins. On touch devices, tap does the same: the details appear under the figures.

## Earlier weeks, the counter, suggestions

These were settled after the builder check; the owner said to continue without stopping.

- **Earlier weeks:** everything time-relative is measured from the selected week's end (Sunday 24:00 Brussels, or now for the current week):
  - the main lift's 8-week window and its "not lately" check
  - "last trained", which means the last gym session before the selected week
  - the 6-week history bars
- **Focus suggestions only on the current week.** Past weeks show none, so old advice never appears. The suggestions come from the unchanged engine: `gym_suggestions(conn, now, limit=20)`, so every muscle it flags as low gets its suggestion. The Overview's focus card shows the top of the same list, so the two never disagree.
- **The counter and the chips are gym-only**, matching the owner's "own layer" choice:
  - The counter reads "N / 20 muscles trained in the gym".
  - The list is headed "No gym work yet".
  - A chip for a muscle that has cardio stripes this week carries a small dot in that sport's colour.
  - The hover panel for such a muscle shows both its cardio minutes and its last gym session.

## Non-goals

- Counting cardio as sets, or changing the focus engine, coverage targets or suggestions.
- Day-by-day replay (direction C from the mockups). Not chosen.
- Editing exercise → muscle mappings here; that stays on Trends → Gym ("Tag your exercises").
- Changes to the Overview or the AI coach.

## Anti-goals

- **Guilt.** No red, no "missed" or "behind" wording. Grey just means "not yet". This follows the main spec's rule.
- A figure that looks like a block diagram. The mockup's blocky shapes were a sketch. The real figure must read as a body with recognisable muscles at a glance.

## Constraints

- **Night Shift style** (Plan 3 tokens, Barlow Condensed + Inter):
  - Shades are new CSS tokens on `:root`: `--muscle-0` grey `#2c3034`, `--muscle-1` `#55682a`, `--muscle-2` `#94bd48`, `--muscle-3` `#c8f169` (the accent).
  - The legend shows all three lime shades plus grey, and the stripe colours for sports present that week.
  - Animations use the existing kit (fill transitions on week change, rise on load) and are all off with reduced motion.
- **The figure** is hand-authored inline SVG in the repo: front and back, 20 tracked muscles, left/right mirrored. No external anatomy assets or libraries (licensing, and it must take the Night Shift colours).
  - Front shows: upper chest, mid/lower chest, front delts, side delts, biceps, forearms, abs, obliques, quads, adductors, abductors.
  - Back shows: traps, rear delts, side delts, triceps, forearms, lats, mid back, lower back, glutes, hamstrings, calves.
  - Non-tracked parts (head, hands, feet, shins, neck) are a neutral body colour.
- **Desktop first:** the main layout targets ≥ 1200 px wide with both figures and the side column in one row.
  - Below 900 px, the figures sit side by side, smaller, and the side column drops below them.
  - At 375 px there's no horizontal overflow.
- **Navigation:** sidebar item "Muscles", directly under Trends. The phone tab bar gains it too; it must still fit at 375 px with no overflow (shorter labels or font size are the builder's call).
- **Data:**
  - **One endpoint**, owner-only like every other route: `GET /api/muscle-map?week=YYYY-MM-DD`. The week is any date in it, defaulting to the current Brussels week. It returns everything the page needs for that week in one response.
  - **Sharing logic:** the set counting reuses the focus engine's rules (shared SQL/helpers, not a copy that can drift).
  - **Timezone:** week boundaries are Brussels Mondays (`timeutil.week_start`), correct across DST changes.
- **Accessibility:**
  - Every muscle shape is focusable and has an accessible name (e.g. "Quads: 0 sets this week, 46 minutes on the bike"), and focus shows the same details as hover.
  - A hidden-by-default "Show as list" toggle renders the same data as a table, as the Trends charts already do.
  - Colour is never the only signal: the panel and list carry the numbers.

## Left to the builder

- **Exact SVG paths:** must meet the anti-goal above.
- **The endpoint's JSON shape:** must cover every item listed under Goals, for all 20 muscles and up to three cardio sports.
- **Hover panel placement:** must stay on screen at the edges.
- **Tab bar fit at 375 px.**
- **Test split:** backend pytest on the endpoint (week boundaries, the sets rule, cardio minutes and the walks exclusion, the main-lift rule, last-trained); Vitest for the shade function and anything else pure; a Playwright pass at 1440 px and 375 px.

## Calls I made (not discussed with the owner)

- **Tab name:** "Muscles", because "Body" already means the measurements page.
- **Swim muscles:** lats, delts and triceps.
- **Stripe strength:** full at 120 minutes a week.
- **Main lift rule:** the 8-week window and the "new" / "not lately" labels.
- **Interaction extras:** click-to-pin, Escape to unpin, the `?week=` URL, the list toggle.
