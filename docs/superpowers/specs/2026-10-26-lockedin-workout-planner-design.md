# LockedIn: Workout planner and training preferences

**Status:** designed in conversation on 2026-10-26. The owner approved the direction, then said "just make it how you think is best", so the details below marked as my calls are mine.
**Builds on:**
- the main spec
- the focus engine: `gym_suggestions`, `_pick`, `muscle_coverage`, the exercise library
- the muscle map
- the AI coach

## Why

The owner wants the app to tell them, right before the gym, what to do differently today. In their words: "yeah you have not trained this so pls do that", and "try this shoulder exercise next time for a different part in shoulder".

- **They have a fixed split, with a Hevy routine per day.** Their Hevy workout titles are "Chest - Schouders - Triceps", "Rug - Bicep" and "Benen - Buik", plus a general day. They know which day they're doing.
- **They read it off their phone and keep logging in Hevy.** There's no Hevy Pro, so no API.
- **They have a bad lower back from injuries.** They don't want lower-back work suggested, and that must be configurable. Exercises that only load the lower back along the way (squats, rows) are fine to suggest; they'll skip them if they want.

## Goals

### Planning a day

1. **Entry points:** a "Going to the gym?" card at the top of the Overview with a **Plan a workout** button, and a **Plan a workout** button on the Muscles page. Both open `/plan`.
2. **Day picker (`/plan`):** one card per routine learned from Hevy (see "Routines"), showing its title as written in Hevy, when it was last done, and how many exercises it has. Plus one extra card: **"Just what I've missed"**.
3. **Tapping a day** shows that day's saved plan, or builds one if none exists. **New plan** rebuilds it.

### The plan

The plan is the routine's exercises in their usual order, with today's changes marked:

- **Weight targets:** each routine exercise gets a target from your last session of it (see "Progression"), shown with what you did last time ("last: 80×8 · 80×8 · 77.5×7").
- **At most one swap (variety):** a routine exercise that's stuck may be swapped for a different exercise for the same muscle. It's shown in place, labelled "Variety", with what it replaces and why.
- **Adds:** up to 2 exercises for muscles that are low and that this day naturally trains. They go in an **"Extra, if you have time"** block at the end.
- **Labels:**
  - Each changed or new item says why, e.g. "Rear delts: 1.5 sets/week, aim 4–12".
  - New-to-you exercises carry "New · start light" and the focus engine's cautious estimate.
- **Per item:**
  - **Swap** replaces it with the next alternative for the same primary muscle.
  - **⋯** has **Don't suggest this again**, which adds the exercise to the never-suggest list and swaps it.
  - **⋯** has **Skip for today**, which greys the item out in the saved plan.
- **Dumbbell weights** follow `profile.dumbbell_weights` (pair totals with per-hand shown, or per hand), like the focus card.
- **The plan is saved.** Reopening `/plan` at the gym shows the same plan until **New plan**, swaps or skips change it.

### "Just what I've missed"

Up to 5 exercises from the focus engine's suggestions, in its order, skipping avoided muscles and never-suggest exercises. No routine, no progression rows.

### Routines

- **Learned from Hevy:** a routine is a workout title used at least once in the last 60 days. Its exercises, in order, are those of the latest counted gym workout with that exact title (Hevy names a workout after the routine it was started from). Titles are matched exactly.
- **Sets per exercise:** the number of non-warm-up sets in that latest workout.
- **Day muscles:** the muscles the routine's exercises hit as primary, plus every muscle in the same `muscles.region` as one of those. E.g. a chest + triceps routine covers chest, shoulders and arms.

### Progression

For each routine exercise, using its latest session:

- **Rep target:** the routine's rep range is 8–12 (bodyweight: the focus engine's rule).
- **Ready to go up:** every non-warm-up set at the top weight hit ≥ 12 reps. The target is the top weight plus one step:
  - barbell, machine, cable or other: +2.5 kg
  - dumbbell: +2 kg per dumbbell (+4 kg on a pair total)
  - bodyweight: no weight, "+1 rep"
- **Otherwise:** the same top weight, labelled "same weight, aim for one more rep".
- **Equipment** comes from the library; exercises missing from the library count as `other`.

### Swaps (variety)

- **Which exercise:** a routine exercise counts as stuck if it's in the focus engine's gym plateaus (`plateaus`). Pick the first stuck exercise in routine order.
- **Its replacement:** another library exercise with the same primary muscle that isn't in the routine, isn't on the never-suggest list, and doesn't target an avoided muscle as primary. Prefer the owner's own history (done in the last 90 days), then exercises related to it in the library, then by library order.

### Adds

- **Which muscles:** day muscles whose `muscle_coverage` status is "low", that no routine exercise hits as primary, and that aren't avoided.
- **Order:** ranked like `gym_suggestions`, taking at most 2.
- **The exercise and weight:** picked with the focus engine's `_pick` rules (own exercise first, else a library one with a related-lift estimate), skipping never-suggest exercises.

### Preferences

A **Preferences** panel on `/plan`, behind ⚙:

- **Leave these muscles out:** chips for all 20 muscles. The planner never adds or swaps in an exercise whose *primary* muscle is left out. Exercises that only hit it as secondary are fine.
- **Never suggest:** a list with "Allow again". The planner never adds or swaps in these.
- **Notes for the coach:** free text, up to 1,000 characters.

Preferences also apply elsewhere:

- **Focus suggestions** (`gym_suggestions`) skip avoided muscles and never-suggest exercises. This also covers the Overview focus card, the coach's `get_focus_facts` and the muscle map suggestions.
- **Muscles page:** avoided muscles are drawn in a neutral "left out" style (not grey-as-untrained), are excluded from "No gym work yet" and from the N / 20 count (which becomes N / 19), and the hover panel says "Left out in your preferences".
- **The AI coach's turn context** lists the avoided muscles, the never-suggest exercises and the notes. The system prompt says to respect them.

### Settled after the builder check (my calls)

- **When a plan goes stale.** A saved plan is current only while all three of these hold:
  - it was built on today's local (Brussels) date
  - the routine's source workout is unchanged (store its activity id)
  - the preferences are unchanged (store a hash of avoid/never)

  Otherwise opening the day rebuilds it automatically. "Skip for today" therefore lasts one day.
- **Comeback.** When the focus engine's `comeback()` fires (7+ days with no counted session):
  - no progression steps: every target is "same weight as last time", labelled "Welcome back: same as last time"
  - no adds and no variety swap
  - the "Just what I've missed" card is hidden

  The Overview card still shows. This matches how the Overview already treats comebacks.
- **"Don't suggest this again"** is offered only on items the planner suggested: adds, the variety swap-in, and "Just what I've missed" items. The owner's routine exercises get **Swap** (today's plan only) and **Skip for today**. Their Hevy routine is theirs.
- **Day muscles:** the regions of the routine's *primary* muscles, plus the routine's *secondary* muscles themselves (no region expansion for secondaries). Push day therefore covers chest, shoulders (including rear delts) and arms. Back day covers back and arms plus rear delts (secondary on rows), but not front or side delts.
- **Bodyweight-tagged exercises logged with weight:** if the latest session's top working weight is > 0, they progress like a weighted lift (+2.5 kg step) and show that weight. This rule lives in the planner's progression only; `gym_suggestions` is unchanged.

### Goals (owner said yes on 2026-10-26)

Goals set with the coach are currently used only by the coach.

- **Linking a goal to a lift:**
  - A goal can name a lift: a new optional `goals.exercise` column (an exact exercise name). The coach's `save_goal` tool gains an optional `exercise` field; the prompt tells it to fill this when a goal is about one lift.
  - **Fallback for goals without `exercise`:** a goal is tied to an exercise if the goal text (case-insensitive) contains the exercise's name without its parenthetical, e.g. "bench press". Failing that, it matches on the first word of that name, if the word is 4+ letters and not one of these: cable, machine, dumbbell, barbell, seated, standing, incline, decline, lying, single, smith.
- **In the planner:** an exercise tied to an active goal is never chosen for the variety swap. The plan shows "Goal: <goal text>" (plus the target, if set) on it.
- **On the Overview:** a small **Your goals** card lists the active goals with their targets and links to the Coach. With no goals, it shows one line: "No goals yet. Set some with the coach." It must not nag.

## Non-goals

- Pushing plans to Hevy, or reading routines from Hevy's API (no Pro).
- Gym mode (one exercise per screen, ticking off sets). The owner logs in Hevy.
- Planning a whole week, or deciding which day to train. The owner knows.
- Editing routines in the app. They come from Hevy.
- AI-generated plans. The planner is rule-based: instant, free, and works without an API key.

## Anti-goals

- **Guilt:** "you skipped legs again" style wording.
- **Unsafe suggestions:** heavy jumps on new exercises, or suggesting work for an avoided muscle.
- **Noise:** a plan that rewrites the whole routine. At most 1 swap and 2 adds, so the plan still looks like the owner's own day.

## Constraints

- **Style:**
  - Night Shift style; the mockup layout is option A, the list.
  - Phone first for `/plan` (read at the gym, 375 px); it works on desktop too.
  - The existing animation kit, off under reduced motion.
- **Data:**
  - Preferences are stored on `profile` (new columns), behind their own `GET/PUT /api/preferences`. The Body page's profile PUT must not wipe them.
  - Plans live in a new `workout_plans` table: id, day title or null for "missed", items jsonb, created_at, updated_at. The latest per day is the current plan. RLS on, anon/authenticated revoked, like every table.
  - Owner-only routes like the rest.
- **Shared rules:** the weights, rounding and new-exercise estimate reuse the focus engine (`_pick`, `_dumbbell_weight`, `_round_down`, `NEW_EXERCISE_FACTOR`), not copies.
- **Accessibility:** buttons with clear names ("Swap Bench Press (Barbell)") and the ⋯ menu operable by keyboard.

## Left to the builder

- The endpoint shapes beyond what's described.
- The internal module split.
- Exact copy, beyond the labels above.
- The look of the "left out" style on the muscle map (it must read as different from "not trained").
- Tests: backend pytest for the routine learning, progression, swaps, adds, preference effects and plan persistence; Vitest for pure helpers and page interactions; Playwright at 375 px and 1440 px.

## Calls I made

- **Learning routines from workout titles** (owner: "make it how you think is best").
- **Dropping gym mode and the in-app day editor** that the mockups showed.
- **The limits:** at most 1 swap and 2 adds.
- **Progression:** the 12-rep rule and its steps.
- **Day muscles** by region.
- **Plan lifetime:** saved plans per day, plus "skip for today".
- **Where preferences live:** on `profile` with their own endpoint.
- **"Just what I've missed":** up to 5 exercises.
