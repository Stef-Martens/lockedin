# LockedIn: Today, session pages, and goals everywhere

**Status:** designed in conversation on 2026-10-26. The owner approved the mockups (`.superpowers/brainstorm/25442-1793048902/content/today-session.html`) and the run and swim additions ("sure looks good"). The owner said goals must be "taken into account everywhere". Details marked as my calls are mine.
**Builds on:** the agenda (Plan 7), the planner (Plan 6), the focus engine, the muscle map, the coach.

## Why

The owner wants to:
- open the Overview and see today's to-dos, ticked when done
- see clearly in the agenda what got done
- open a planned session as a real page that shows the plan before and how it went afterwards (instead of the small pop-up)
- have their coach goals steer the whole app, not only the coach's own judgment

## Goals

### 1. Overview: the Today block

- **Replaces the current Today card,** at the top. It is a list of today's agenda items. Each has:
  - **a check circle:** lime with a tick when done, an empty ring when not
  - **the title, and the goal it serves** (tag), if it has one
  - **a one-line result when done** (see "Result line")
  - **an action:**
    - **"See how it went"** when done, which opens the session page
    - **"Plan it"** for open gym items with a routine, which opens the planner
    - otherwise **"Open"**, which opens the session page
- **Header:** "N of M done". Under the list, one line with tomorrow's items (and the day after's, if tomorrow is empty).
- **Nothing planned today:** the block says so in one line, with a link to the agenda.

### 2. Overview: goals card with progress

Each active goal shows a progress bar when it can be measured, using the rules in "Goal progress". Otherwise it shows its text and target only. The focus tips and the Today items carry goal tags.

### 3. Agenda: done is obvious

- **Done items:** a green-tinted card with a tick before the title, and the result line instead of the summary.
- **Missed items:** past and not done (and not rest or other) fade to 65% opacity and say "Not done". There's no red.
- **Clicking an item opens `/agenda/:id`,** the session page. The pop-up edit sheet goes away; editing happens on the session page. **+ Add** keeps its sheet.

### 4. The session page `/agenda/:id`

- **Header card:**
  - a big check (done) or a dashed "to do" circle
  - the date, the sport, "planned with the coach" or "added by you"
  - the title and the goal tag
  - the Zwift status (bike items with blocks)
  - Edit (title, note, optional, day as any date, targets for run and swim), Move (a date input) and Delete (with confirm)
  - when done: "Full activity →", which opens `/activities/:id`
- **Before (not done), by sport:**
  - **Zwift workout:**
    - **A chart of the blocks** with an FTP line.
    - **A table of the parts:** each part, its time range (mm:ss–mm:ss), its power in W (a range for ramps), and its label (Warm-up, Interval n, Recovery, Steady, Cool-down, Free ride).
    - **Stats:**
      - **Duration.**
      - **Sweet-spot minutes:** minutes at 84–97% FTP.
      - **Estimated TSS:** Σ(duration_h × IF² × 100), with IF = the part's average fraction.
      - **The FTP used.**
    - The note.
  - **Run:** the targets (distance or duration, pace range in min/km, HR zone with its bpm range from the max HR) and the note.
  - **Swim:** the targets (distance, pace range per 100 m) and the note.
  - **Gym:** the plan for that day if one was built (`workout_plans` for that routine, built on that date). Otherwise the routine's exercises with their targets as the planner would build them for that day. Plus a "Plan it" link (today or in the future).
  - **Rest or other:** the note.
- **After (done), against the plan:**
  - **Zwift (bike):**
    - **Stats:** time, average power, intervals (the average across work parts against the target, with "on target" if within 3%), average HR, TSS (the activity's own if present).
    - **The chart:** the activity's power over time, 30 s smoothed, with the planned target as a dashed line and HR as a second line. Work parts are shaded. The planned parts are aligned to the start of the activity.
    - **Interval table** for each work part (power ≥ 75% FTP): target W, average W, average HR, average cadence, and On target / Above / Below (±3%).
    - Without a block plan (a note-only ride): the activity's stats only.
  - **Gym:** a table with one row per exercise: planned (sets × reps at weight) and what was done (the logged non-warm-up sets).
    - **✓** when every planned set was done at the planned weight or more and in the rep range or above.
    - **"close"** when there are fewer sets, a lower weight, or fewer reps on some sets.
    - **"skipped"** when nothing was logged.
    - Extras are marked as extra. Exercises that were logged but not planned are listed as "added".
  - **Run:**
    - **Totals against the targets:** distance, time, average pace, average HR.
    - **A pace chart** with the target pace band.
    - **Splits per kilometre** (from the distance stream): pace and HR, "on target" when the pace is inside the band.
    - **Time in HR zones 1–5** (from the HR stream and the max HR).
  - **Swim:** totals against the targets: distance, time, pace per 100 m, lengths, strokes, average HR.
  - **No stream data:** the charts and splits are hidden; the totals still show.

### 5. Agenda targets for runs and swims

- **New optional `targets` on agenda items:** `{distance_m?, duration_s?, pace_low?, pace_high?, hr_zone?}`.
  - Paces are seconds per km for runs and seconds per 100 m for swims.
  - `hr_zone` is 1–5, runs only. Targets are allowed only on run and swim items.
  - **Limits:** distance 100 m–100 km; duration 60 s–6 h; pace runs 150–720 s/km, swims 50–300 s/100 m; `pace_low` ≤ `pace_high`.
- The coach's `save_agenda` accepts `targets`. The prompt asks for them on runs and swims.

### 6. Goals everywhere

- **Goal areas:** `goals.area` is limited to `gym | bike | run | swim | body | general` (existing values are mapped; unknown ones become `general`). `save_goal` gets the enum, and the coach sets it.
- **Goal progress** (`lockedin/goals/progress.py`, shown on the Overview card and given to the coach in `get_goals`): `progress(goal) -> {current, target, unit, label} | None`. It finds the first number in the goal's text (else its target) with a unit:
  - **A goal with `exercise` and a kg number:** the best e1RM of that exercise in the last 8 weeks against the number. The label is "96 / 100 kg est. 1RM".
  - **Area bike and a W number (or the word FTP):** current `ftp_at` against the number.
  - **Area run and a km or K number:** the longest counted run in the last 8 weeks (km) against the number.
  - **Area swim and an m or km number:** the longest counted swim in the last 8 weeks against the number.
  - **Area body and a kg or cm number, with a measurement name in the text** (weight, chest, waist, arm…): the latest value of that measurement against the number. The bar fills toward the target from the first measurement.
  - **Otherwise:** None.
- **Focus tips:**
  - **Gym:** among low muscles, the primary and secondary muscles of active goal lifts come first. Their reason ends with "· helps: <goal>", and each item gets a `goal` field.
  - **Sessions:**
    - **Active run goal:** a run session suggestion is always included, the existing rule's if one fires, otherwise "Steady run 40′" in zone 2 (with HR bpm). It's tagged with the goal and listed first among session suggestions.
    - **Active bike goal:** the same for a bike session, otherwise the intervals suggestion.
    - **Swim goals:** "Swim 30′ steady".
  - **Overview interleaving:** goal-tagged items come first.
- **Planner:**
  - **A routine exercise tied to an active goal** (`goal_for`) gets one extra working set, capped at 5. Its reason says "+1 set for your goal".
  - **Adds:** muscles of active goal lifts rank first among low day muscles.
  - **The comeback rule wins:** no extra set during a comeback.
- **Muscle map:** each muscle gets `goals: [labels]` for active goal lifts that train it (primary or secondary). The hover panel shows "Works toward your goal: …".
- **Agenda:**
  - Items get an optional `goal_id` (fk goals, on delete set null). The coach sets it in `save_agenda`.
  - Items show the goal tag: in the agenda, on Today, and on the session page.
  - The item add and edit API accepts `goal_id` (an active goal) as well.
- **Coach prompt:** plans should serve the active goals. When adding agenda items, it links them with `goal_id`. When suggesting sessions, it says which goal they serve.

### Settled after the builder check (my calls)

- **Goal extra set:** a goal lift gets +1 working set only when its latest top-weight sets were 3 or fewer, so 3 becomes 4 and stays 4. This avoids creeping up as the extra set feeds back into "last time".
- **Gym "after" without a saved plan:** compare against the routine items of `build_plan(conn, start_at − 1 min, title)`, meaning the routine exercises and their targets as they stood just before the session. Extras and swaps are left out. With a saved plan, its items count, and items the owner skipped in the planner show as "skipped by you", not as missed.
- **Goal lift:** `goal_lift(conn, goal)`. That's `goal.exercise` if it's set, else the one logged exercise (last 90 days) that `goal_for` ties to the goal. If several or none match, the goal has no lift. Lift progress, gym focus priority, planner adds and the muscle-map tags all use it.
- **FTP for after targets and the ±3% check:** `ftp_at(ride start)`, the app's FTP everywhere. The page names the FTP it used. If `ftp_override` isn't set, it adds "Set your Zwift FTP on the Body page so this matches Zwift."
- **Body goals:**
  - **Fixed targets** ("78 kg", "40 cm arms"): the bar fills from the measurement at goal creation (the latest one on or before it, else the first after) toward the target.
  - **Relative goals** ("lose 5 kg", "+2 cm", "gain", "drop"): no bar (None).

### Result line (agenda, Today)

- **bike:** "Done · 66′ · 128 W", plus " · intervals on target" when every work part is on target.
- **run:** "Done · 8.2 km · 5:42/km".
- **swim:** "Done · 1500 m · 2:05/100 m".
- **gym:** "Done · N exercises · 52′".
- **Missing values** are left out.

## Non-goals

- "Last time you did this kind" history on the session page (dropped from the mockup).
- Editing Zwift blocks in the UI (they come from the coach).
- Run and swim interval structures (intervals go in the note).
- Goals created outside the coach (no goal form).
- Changing how ticking off works.

## Anti-goals

- Red, "failed" or guilt wording for missed or below-target sessions. Use "close", "below" and "not done".
- Goal tags that clutter every item: only items with a goal show one.
- Wrong numbers. Where a value can't be computed (no streams, no FTP, no max HR), hide the comparison rather than guess.

## Constraints

- **Night Shift style,** the existing chart conventions (`SeriesChart` patterns: 30 s display smoothing, `syncId`), reduced motion, 375 px with no overflow.
- **One request per page:** `GET /api/agenda/{id}/detail` returns the item, `plan` (sport-specific) and `actual` (null if not done), with every number already computed.
- **Shared logic, not copies:** stream downsampling and zones reuse `focus/zones.py`, `fitness.ftp_at` and the agenda store's tick-off.
- **Migration:** `agenda_items.targets jsonb`, `agenda_items.goal_id bigint references goals on delete set null`, and the `goals.area` check plus data mapping.

## Calls I made

- **Goal-type mapping and progress parsing rules**, as above.
- **On target:** within ±3%.
- **TSS and sweet-spot formulas**, as above.
- **Alignment:** planned parts aligned to the ride start.
- **Planner:** the goal lift gets +1 set, capped at 5.
- **Default goal sessions:** "Steady run 40′ zone 2", "Swim 30′ steady", and the intervals suggestion for bike.
- **Missed items** fade to 65%.
- **The edit sheet** moves onto the session page.
