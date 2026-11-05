# LockedIn: the coach's verdict on your last workout

**Status:** designed in conversation on 2026-11-04. The owner approved the description ("sure i guess"). Details marked *(my call)* are mine.
**Builds on:** the coach's model client and daily budget, the session page's plan-versus-actual (`agenda/detail.py`, `agenda/actual.py`), the Overview page.

## Why

After a workout, the owner opens the coach and asks "what did you think of my last workout?". They want that answer already waiting on the dashboard: how it went, and how on point it was against the plan ("so long at this heart rate or speed").

## Goals

1. **A "Last workout" card on the dashboard** shows a short verdict from the coach on the latest workout, without being asked.
2. **It says how the workout compared with the plan,** with the real numbers: per block, part or exercise where the data has them.
3. **It updates by itself** when a new workout comes in.
4. **It's written once per workout and saved,** so reopening the dashboard is instant and costs nothing.

## Non-goals

- Verdicts on sessions that were skipped. This is about workouts that happened.
- Chatting from the card. The coach page stays where questions go.
- The chat coach reading or quoting verdicts.
- Advice on what to change in the plan. The verdict looks back; one forward-looking remark is fine, changing the agenda isn't.
- Rewriting a verdict because later data changed the comparison, such as a new max HR or FTP. (Filling in a workout's watch laps is the one exception, once.)

## Anti-goals

- **Numbers the data doesn't contain.** A made-up pace is worse than no verdict.
- **The dashboard waits on the model.** The rest of the page must load at its normal speed, and a failed verdict must never break it.
- **Costs that creep up.** Opening the dashboard repeatedly, from two tabs, or while a verdict is being written must never cause a second paid call.
- **Calling a workout "not planned" when it was.**

## The card

Placed above the Today block on the Overview page *(my call)*:

- **Header:** "Last workout", the day, sport and title (the agenda item's title, or for example "Run" when nothing was planned), and a link "See how it went". It goes to the session page when an agenda item is ticked by this workout, else to the activity page.
- **Label:** `On plan`, `Close to plan` or `Off plan`. A workout with no plan gets a neutral `Not planned` instead.
- **Text:** 2 to 4 sentences, starting with how it went. Example, with invented numbers: "Tempo run, 4 × 5′. Three of the four blocks were inside 5:30–5:50; the last one drifted to 5:58. Heart rate stayed in zone 4 until that last block, so the pace was about right."

**States:**
- **No workout, or the latest is more than 14 days old:** no card *(my call: an old verdict on the dashboard is noise)*.
- **Being written:** the header plus "The coach is looking at it…". The rest of the page is already usable.
- **No API key:** no card. The dashboard stays as it is today.
- **Over the daily budget:** the header plus "Today's coach budget is used up; this appears tomorrow." It's retried on the next open after midnight.
- **The model failed:** the header plus "Couldn't write this one; it tries again next time you open this page." At most one attempt per workout per 15 minutes, so a broken API can't run up calls *(my call)*.

**Two workouts in a day:** the card shows the latest. The earlier one gets its verdict on its own page (below).

## The session and activity pages

A done session's page, and the activity page of a workout that ticks no item, show the same label and text at the top *(my call: same component)*. They use the same save-once rule, so opening a page may write its verdict.

Only workouts from the last 14 days get a new verdict *(my call: browsing old sessions must not spend money)*. Older ones show one only if it was already saved.

## What counts as the last workout

The newest activity by `start_at` that passes `COUNTED_SQL` (not superseded, not a walk). When an activity is superseded by a better copy (the same ride from Zwift and from HealthFit), the new copy gets its own verdict, so at most one extra call.

## When it's written

The first time a page asks after the workout arrives, not when the workout is uploaded *(my call)*:
- Vercel functions can't reliably run work after responding.
- The sync would slow down, and Hevy imports of many workouts would pay for verdicts nobody reads.
- Only workouts the owner looks at cost anything.

The page loads the verdict separately from `/api/overview`. It sees "writing" and checks again every 3 seconds, for at most 90 seconds, then leaves the "being written" text in place until the next visit *(my call)*.

**One paid call per workout.** A database row claims the work before the model is called. Whoever inserts the claim makes the call; everyone else sees "writing". A claim older than 6 minutes counts as abandoned and can be taken over (the function was killed) *(my call: the same length and reason as the coach's `TURN_LOCK`, longer than the function's 300 s limit, so a slow call that's still running is never paid for twice)*. No database connection or transaction stays open during the model call (the coach route already avoids this; follow it).

**A plan added or removed afterwards.** A verdict is written again in exactly two cases *(my call)*:
- It was written as `unplanned` and the workout now ticks an item. This is what keeps anti-goal 4.
- It was written against a plan and the workout now ticks no item, because the item was deleted.

When a workout ticks a different item than before, nothing is rewritten. The agenda's matching is day-wide, so a second workout that day can swap which item ticks which, and that must not pay to rewrite older verdicts. Editing an item's targets doesn't trigger a rewrite either.

**A workout on a rest day** ticks the rest item, because a rest day takes whatever was done. A rest item isn't a plan for that workout, so it counts as `unplanned` *(my call)*. The facts mention it was a planned rest day, so the coach can say so. A planned session of a different sport never ticks an item (the agenda's matching needs the same sport).

## What the model gets

One call, no tools. All facts are prepared by the server as JSON and put in the request; there's no SQL and no chat history:

- **The workout:** sport, date, time, distance, duration, moving time, average HR, power, pace, TSS, as on the session page (`act.activity` and the `actual` block of `detail()`), without the raw chart series.
- **The plan,** when an agenda item is ticked: title, note, optional, and `plan` from `detail()`. For a run, its `targets` with `steps` and bpm for zones. For a ride, the Zwift parts. For gym, the routine's items.
- **The comparison the app already computes:** run splits against the pace band and time in each HR zone; ride parts and intervals on target; gym rows.
- **Recent similar sessions:** the last 3 counted sessions of the same sport before this one, with date and main numbers, so it can say "faster than last week at the same heart rate".
- **Context:** the `easy_back` note (first two weeks after time off), and the owner's active goals as one line each.

**Per-block running data comes from the watch's own laps** *(changed 2026-11-05, replacing an earlier approach of placing the plan's steps on the run's data)*. A workout started from a planned run records one lap per step, with its `wkt_step_index`, `intensity` and exact time, distance and heart rate, so nothing is guessed. A run without such laps gets km splits, zones and totals, and the verdict doesn't speak about blocks. See "Watch laps" below.

**Rules in the prompt:**
- Use only numbers present in the facts.
- Never guess at what's missing, and mention it only if it changes the verdict (no heart rate, no splits).
- Plain words, 2 to 4 sentences, no headings or lists, no praise for its own sake. Say plainly when it went badly.
- Don't give medical advice. On a session after time off, compare with the easy-back note.

**Label meaning**, given to the model:
- `on_plan`: done as planned, targets met within reason.
- `close`: mostly as planned, with a clear miss.
- `off_plan`: a different session from the plan, or targets clearly missed.
- `unplanned`: set by the server when no item is ticked; the model doesn't choose this.

The result should come back as structured data (label and text), using whatever the API documents for that on this model. The builder confirms this against the `claude-api` skill rather than from memory, and it must work together with the client's existing settings (adaptive thinking, fallbacks).

**Client and cost.** It uses the same model client as the coach (`get_llm`, `CoachLLM`), so tests can replace it. Each call is recorded in `coach.usage` with `conversation_id` null, and counts towards `coach_daily_budget_usd` the same way. At current prices ($4 in, $20 out per million tokens on Opus 5.5), expect about 2 to 4 cents per verdict *(this corrects the "a cent or two" said in conversation)*. The builder measures one real call if a key is available.

## Watch laps

Checked against a real file from the owner's watch (2026-11-04, tempo 3 × 8 min): 8 laps, `lap_trigger: time`, `intensity` warmup/active/recovery/cooldown, `wkt_step_index` 0,1,2,1,2,1,2,4, and each planned step exactly its planned length.

- **Stored at import** as `activities.laps` (jsonb, a list; `[]` when the file has none, null when never read).
- **Blocks:** laps with a step index, in order. They follow the plan when each lap's kind matches the planned step at that position and there are no more laps than steps; only then does a block get its plan's goal, target and `in_target`. Otherwise the blocks are shown without judging them against the plan.
- **On the session page:** a table of the blocks. On a run with steps, km splits lose their faster/slower labels, because the plan's band belongs to the work blocks only.
- **Older runs:** the Mac can upload recent files again. A known file whose activity has null laps gets them filled in, and that workout's verdict is deleted so it's written again from the laps.

## Data

New table `workout_verdicts` (migration):
- `activity_id` primary key, references `activities`, deleted with it
- `item_id` the agenda item compared against, null when none
- `label`, `body` (null until written)
- `claimed_at`, `written_at`, `failed_at`
- `model`

Not added to what the coach's `run_sql` can read *(my call: see non-goals)*; check how the read-only role's grants work and keep it out.

**Deleting a verdict's item:** the foreign key sets `item_id` to null. Whether the verdict is out of date comes from its `label` and what the workout ticks now, as above, not from this column.

## API

- `GET /api/verdicts/latest` returns `{activity, verdict}` or `{activity: null}`.
- `GET /api/verdicts/{activity_id}` returns the same for one workout, or 404.
- `verdict.status`: `done` (with `label`, `text`), `writing`, `over_budget`, `failed`, or `none` (too old and never written).
- Owner login only (`require_owner`). Not on the sync token or the watch token.

A GET that may write is a deliberate choice here: the owner is the only user, and it's what "automatically there" needs. The response must say `no-store`, so nothing caches a "writing" state.

## Later (not now)

Writing at upload time, a weekly summary, or a verdict in the iPhone app.
