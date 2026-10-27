# LockedIn: time off (vacations, an operation)

**Status:** designed in conversation on 2026-10-27. The owner approved the description ("sure sounds good"), and asked for entry both through the coach and on a page ("maybe both"). Details marked *(my call)* are mine, including the answers to a builder review (no "light only" mode, protected streak weeks, forecasts on training time, easing back into endurance sports).
**Builds on:** the agenda and its coach tools (Plan 7), the planner (Plan 6), the focus engine and muscle map, goals and the Forecast page.

## Why

The owner has vacations coming and an operation "in some time". After the operation they can still do some things, but not everything, and each restriction lasts a different time. The example they gave: "can't run for 15 days, but can't do upper body for a month". Today the app doesn't know any of this. The coach would plan runs the week after surgery, the focus tips would nag about untrained chest, the streak would break, and the forecasts would read the gap as "stopped improving".

## Goals

1. **The owner can record time off,** by telling the coach in a sentence or by filling in a card on the Agenda page.
2. **The whole app respects it.** Nothing restricted gets planned or suggested while it's off, nothing nags about it, and the streak and forecasts treat it as time away, not as failure.
3. **Coming back is gentle.** When a restriction ends, the activity comes back lighter and easier, not at the old numbers.

## Non-goals

- Medical advice. The app records what the owner says they can't do and until when. It never decides what's safe after an operation, and the coach doesn't suggest how long recovery should take. If asked, it says to follow the surgeon or physio.
- Notifications or reminders about time off.
- Partial-intensity rules (e.g. "running allowed but only easy"). An activity is either off or fine *(my call)*.

## Anti-goals (would make this a failure even if it works)

- Anything restricted shows up as planned, suggested, or "you're low on…" during its window.
- The streak or a goal forecast punishes the owner for an operation.
- Something the owner planned gets silently deleted.

## The model

A **time-off entry** has:
- **reason:** `vacation` or `injury` (shown as "Vacation" / "Operation or injury") *(my call: one "injury" kind covers operations)*
- **label:** optional free text, e.g. "Knee operation", "Mallorca"
- **start:** a date; the entry ends on its latest `until`
- **restrictions:** a list of `(category, until)`, where `until` is the last day it's off (inclusive). Categories:
  - `run`, `bike`, `swim`
  - `upper` (gym: arms, back, chest, shoulders muscle regions)
  - `core` (gym: abs, obliques)
  - `lower` (gym: legs region)
  - `all` (everything above)
The owner's example becomes: injury, start 3 Dec, restrictions `run until 17 Dec`, `upper until 2 Jan`. A plain vacation becomes: vacation, start 20 Dec, `all until 27 Dec`.

**"Off on day D"** means: some entry has `start ≤ D ≤ until` for that category (or for `all`). **"Away on day D"** means `all` is off on D. Several entries may overlap; the union applies.

## Entering it

### Coach
- **New tools:** `save_time_off` (create, change or delete an entry) and the current entries in every chat's context (as agenda and goals are now).
- **Same agreement rule as goals and the agenda:** the coach reads the entry back in plain words ("Operation 3 Dec: no running until 17 Dec, no upper body until 2 Jan. Save?") and only calls the tool after the owner agrees.
- **It turns sentences into dates:** "for 15 days" from 3 Dec is until 17 Dec; "a month" is the same day next month minus one. It asks when the start date is unclear.
- **Its advice respects the limits** while they're on: it never proposes a restricted activity in a window and offers what's allowed instead.

### Agenda page: Time off card
- **The list:** current and upcoming entries (past ones hidden) *(my call)*, each as one line: "Operation · from 3 Dec · no running until 17 Dec, no upper body until 2 Jan", with edit and delete.
- **Add / edit:** reason, label, start date, then each category as "fine" or "off until [date]". Vacation has a shortcut, "Everything off from … to …".
- **The week view:** days inside a window get a thin band at the top: "Operation · no running, no upper body" or "Vacation".

## What respects it

### Agenda and coach planning
- **New items:** the coach's `save_agenda` refuses an item whose sport or routine is off on its day, with a plain message the coach can relay. A gym routine counts as off when most of its working sets hit restricted muscle regions *(my call: by primary muscle, >50% of the routine's sets)*.
- **Manual adds** on the Agenda page are allowed, but show a warning ("Running is off until 17 Dec") *(my call: the owner may know better)*.
- **Existing items that clash** get a flag in the week view and on the session page ("Clashes with your time off"). They're never deleted or moved.
- **Zwift workouts** for days when bike is off aren't sent to the Mac.

### Planner (gym)
- **While upper/core/lower is off,** a day's plan drops exercises whose primary muscle is in a restricted region, and adds no extras for those muscles. If nothing is left, the planner says so ("Upper body is off until 2 Jan; nothing left of this routine") instead of building an empty plan.
- **Coming back:** when a restriction ends, those lifts start lighter. The planner's per-lift staleness (−10% after 3 weeks, −20% after 8) already does this for lifts not done in a while. For time off, the same easing applies from the first day back even if the gap was under 3 weeks *(my call)*.

### Coming back to running, cycling, swimming
- **For 2 weeks after a `run`/`bike`/`swim` (or `all`) restriction ends,** the coach plans that sport easy only (no intervals, run HR zone ≤ 2, Zwift parts ≤ 75% FTP), and says why ("first two weeks back after your operation"). `save_agenda` doesn't refuse harder sessions in that window, but the session page shows a note *(my call: easing by guidance and a visible note, not new rules in Zwift rendering)*.

### Focus tips, Muscles page, streak
- **Focus tips** skip restricted muscles and sports while they're off, and skip everything while away.
- **Muscles page:** restricted muscles show "Off until 2 Jan" instead of "no gym work yet", and don't count as low.
- **Streak:** a **protected week** is one with 4 or more days inside any time-off entry (vacation or injury, whatever is restricted). A protected week counts when it has the usual 2 sessions; otherwise it's skipped over and doesn't break the streak *(my call)*.
- **Comeback card** ("Welcome back"): after a vacation (away 7+ days) it says "Back from vacation". In the 14 days after an injury restriction ends, it says "Back from your operation" (or the entry's label) even if the owner kept training other things. This changes the card's wording only; the planner's welcome-back mode still follows the 7-days-without-sessions rule, and restricted lifts are eased by the per-lift rule above *(my call)*.

### Forecast page
- **Each goal has a category:** lift goals by their lift's primary muscle region (`upper`/`core`/`lower`), FTP and bike goals `bike`, run goals `run`, swim goals `swim`, body goals none. `all` covers every goal.
- **Goal forecasts run on training time:** days when the goal's category was off are cut out of the time axis before fitting, so a month off neither flattens the slope nor shows as a flat stretch. History points from those days are dropped. *(My call: closing up the axis, not only dropping points, because the history already skips empty weeks.)*
- **The projection** maps training time back to calendar days: the trend pauses through any future window when the goal's category is off, then adds no gain for 2 more weeks ("settling back in"), and the ETA moves back accordingly *(my call)*.
- **Fitness ahead:** planned load is zero for clashing items in a window. The dip shows honestly.
- **The charts** shade time-off windows.

### Overview
- **Today block:** during time off, one line under the header: "Time off: no running until 17 Dec, no upper body until 2 Jan" (or "Vacation until 27 Dec").

## Constraints

- **Deploy order:** the new table's migration goes to Supabase before the code reaches `main` (pushing `main` deploys).
- **Time zone:** all days are Brussels days, like the rest of the app.
- **The coach's read-only SQL role** may read the new table, like `goals`.
- **No worktrees:** work happens on `main` in the main checkout.

## Left to the builder

- Table and column names, and the API shape (one resource under `/api/time-off` is the obvious choice).
- How the restriction check is shared (one helper, e.g. `off_on(conn, day) -> set[category]`, used everywhere).
- The exact copy of messages, following the app's plain, short style.
- Visual details of the Time off card and the week-view band, using existing components and tokens.
