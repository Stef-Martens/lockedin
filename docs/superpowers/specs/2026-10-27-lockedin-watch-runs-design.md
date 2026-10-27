# LockedIn: planned runs and swims on the Apple Watch

**Status:** designed in conversation on 2026-10-27. The owner approved the description ("sure looks good"). The owner wants the watch to guide "all of it": warm-up, work, recoveries, repeats and cool-down. The coach plans the runs. Details marked *(my call)* are mine.
**Builds on:** the agenda and its coach tools (Plan 7), heart-rate zones (focus engine), the Forecast page's "fitness ahead".

## Why

The owner builds each structured run by hand in the watch's Workout app before going out. LockedIn already knows the plan, since the coach put it in the agenda. Today a planned run is only one block: distance or time, a pace range and a heart-rate zone. There are no steps, so even a perfect export couldn't tell the watch "4 × 5 min at tempo, 2 min jog".

## What a spike proved (2026-10-27)

We built a throwaway iPhone app with WorkoutKit, signed it with the owner's free Apple ID and installed it. The watch is an older model on **watchOS 10.6.2**, its last possible version. The iPhone is on iOS 27.

- **Works.** `.workoutPreview(plan, isPresented:)` (SwiftUI, from WorkoutKit) shows Apple's sheet. The owner taps **Add to Watch** and the run appears in the watch's Workout app with all its steps and pace alerts. This works with a free Apple ID and needs no watch app.
- **Doesn't work.** `WorkoutScheduler.schedule(_:at:)` accepted 4 runs, and the phone listed them. None appeared on the watch. The likely causes are that a watch app is needed, or that a watchOS 10 watch doesn't get them from iOS 27. We couldn't test either: Xcode 27 can't see the watch, so a watch app can't be installed.

- **Swims (tested the same day).** A pool swim with one distance goal (`SingleGoalWorkout(activity: .swimming, swimmingLocation: .pool, goal: .distance(1500, .meters))`) reached the watch through the preview sheet. A structured swim (a `CustomWorkout` with swimming steps) did not, although the phone reports support for it. Structured swims most likely need watchOS 11, which is also when the pool-swim interval goal `poolSwimDistanceWithTime` arrived.

So this design uses the preview sheet: **one tap per run or swim**. Fully automatic sending is left for when the owner has a newer watch (see Later).

## Goals

1. **Planned runs carry their full structure,** written by the coach: warm-up, repeat blocks of work and recovery steps, and cool-down. Each step has a length and a pace or heart-rate target.
2. **The owner sees the structure** on the agenda and the session page.
3. **A small iPhone app** lists today's and the next 7 days' planned runs. A tap opens Apple's sheet, and **Add to Watch** puts the run on the watch exactly as structured.
4. **Reinstalling is one command** when the free account's 7-day signing runs out.

5. **Planned swims go to the watch too,** as a pool swim with the planned distance as its goal. The owner asked for this after approving the run design.

## Non-goals

- Rides (Zwift has its own workout files) and gym.
- Steps or pace alerts for swims. The owner's watch can't take them (see the spike). The coach's swim set stays in the note.
- Automatic sending to the watch without a tap.
- Editing steps on the web. The coach writes them; the owner asks the coach to change them *(my call)*.
- An App Store or TestFlight build. It's a free Apple ID, installed from the Mac.
- Reading back from the watch which runs were added. WorkoutKit can't report what the owner tapped in Apple's sheet.

## Anti-goals

- **A run looks different on the watch than in LockedIn.** That means a different structure, pace or heart-rate numbers.
- **Editing a run on the web silently drops its steps.**
- **The phone's key can write anything or read more than planned runs.**

## The steps

They mirror how WorkoutKit's `CustomWorkout` is shaped, so the iPhone app maps them one to one *(my call)*. Steps are stored inside the run's existing `targets` jsonb as `targets.steps` *(my call: no migration, and runs without steps keep working)*:

```json
"steps": {
  "warmup":   {"goal": {"time_s": 600}, "target": {"hr_zone": 2}},
  "blocks": [
    {"repeat": 4, "steps": [
      {"kind": "work",     "goal": {"time_s": 300},       "target": {"pace_low": 330, "pace_high": 350}},
      {"kind": "recovery", "goal": {"time_s": 120}}
    ]}
  ],
  "cooldown": {"goal": {"open": true}}
}
```

- **warmup / cooldown:** optional, one step each.
- **blocks:** 1–10 blocks. Each has `repeat` 1–20 and 1–10 steps. Each step's `kind` is `work` or `recovery`.
- **goal:** exactly one of `time_s` (30 s–3 h), `distance_m` (50 m–50 km) or `open: true` (until the owner presses next).
- **target:** optional. Either `pace_low` + `pace_high` (s/km, the same rules and run pace limits as today's targets, low = faster), or `hr_zone` 1–5. Not both.
- `steps` is allowed only on runs.

**With steps, the summary comes from the steps** *(my call: one source of truth, so LockedIn and the watch can't disagree)*. The run's other targets (`distance_m`, `duration_s`, `pace_low/high`, `hr_zone`) are recomputed by the server on every save. Anything sent for them is ignored. They still drive the Edit form's display, the session page's plan-versus-actual (`agenda/detail.py`) and the planned load.
- `duration_s`: the total time, when every goal is a time.
- `distance_m`: the total distance, when every goal is a distance.
- `pace_low` / `pace_high`: the fastest and slowest pace across the work steps that have one.
- `hr_zone`: the work steps' zone, when they all share one.
- Anything that doesn't fit these rules is left empty.

**Changing a run that has steps** *(my call: in the store, so the web and the coach behave the same)*:
- A change whose `targets` doesn't mention `steps` keeps the existing steps.
- `"steps": null` removes them, turning the run back into one block with whatever summary targets the change gives.
- `targets: null` clears everything, steps included.
- Changing the sport away from run is refused while steps remain, the same as targets on a non-run today.

**Heart-rate zones become beats per minute** when sent to the watch, using LockedIn's own zones (`HR_ZONE_STARTS`, % of max HR) and the owner's max HR as of today (`max_hr_at`, override first). Zone 1 is 60–72 %, zones 2–4 run up to the next zone's start, and zone 5 is 92–100 %. The watch's own zones are not used, because they would differ from LockedIn's (anti-goal 1). The server does this conversion in the feed, so the app has no zone logic. With no max HR known, a heart-rate target is left off the step, and the summary line says so.

**One-line summary** (server-side, shown on the web and in the app):

> 10' warm-up Z2 · 4 × (5' @ 5:30–5:50, 2' jog) · cool-down

The format, the rounding and the units are the builder's to choose. It stays short; minutes and km are the units the owner reads.

## The coach

- `AGENDA_CHANGE.targets` gains `steps` with the schema above. The tool description says when to use it: for any run with structure (intervals, tempo blocks, progression), and leave it out for an easy run with one target.
- The schema doc for `agenda_items` mentions `targets.steps`.
- The tool description and the coach prompt (which today says "give runs targets") say three things:
  - With steps, the summary targets are worked out by the server, so the coach doesn't need to send them.
  - To change a stepped run's pace, the coach changes the steps.
  - To make it a plain run, the coach sends `"steps": null`.
- **Validation happens server-side, like today's targets.** A bad structure (empty blocks, two goals, pace out of range, steps on a non-run) is refused with a message the coach can fix from.

## Web

- **Agenda item and session page:** a planned run with steps shows the one-line summary under the title.
- **The session Edit form, for a run with steps:**
  - The summary target fields are replaced by the one-line summary and "Ask the coach to change the steps". The derived summary can't be edited by hand, which would undo it (anti-goal 1).
  - Title, day and note stay editable.
  - The form never sends `steps`, so they're kept (anti-goal 2).
- **"Fitness ahead"** (`forecast/ahead.py` `planned_load`): a run with steps uses its total time. Distance steps are converted to time using their pace, or the run's pace, or skipped. Each step's intensity comes from its pace or zone, so a 4 × 5' tempo counts as harder than an easy run of the same length *(my call; the exact mapping is the builder's, kept in line with the current `ZONE_IF` approach)*.

## The feed

`GET /api/watch/runs`, read-only:
- **Auth:** `Authorization: Bearer <WATCH_TOKEN>`, a new env var, separate from `SYNC_TOKEN`, so the phone's key can't upload (anti-goal 3). It follows the same rules as the sync token: at least 16 characters, compared in constant time. The owner's normal login also works, for testing from the web.
- **Returns** today's and the next 7 days' planned runs, in day order:
  - items that aren't done
  - with optional runs included and marked
  - without runs that clash with time off

  Per run: `id`, `day`, `title`, `optional`, `summary`, and `workout`, ready for WorkoutKit. Workout fields:
  - `display_name`: the title
  - `location`: `outdoor` *(my call; the agenda has no indoor/outdoor today)*
  - `warmup`, `blocks`, `cooldown`, with goals and alerts already in final form: pace as a speed range in m/s, heart rate as a bpm range
  - **Runs without steps:** one work block of one step, using the run's distance or duration and its pace or zone. With neither, an open goal.

**Swims** come in the same list, in the same order and with the same filters. Each has `id`, `day`, `title`, `optional` and `note`, plus a summary like "1500 m" or "1500 m @ 2:00/100 m". Its `workout` has a different shape, a single-goal pool swim:
- `kind: "swim"`, `location: "pool"` *(my call; the agenda has no pool/open-water field)*.
- `goal`: the swim's `distance_m`, else `duration_s`, else open.
- No pace alert: a single-goal workout has none.

Run workouts carry `kind: "run"`, so the app knows which WorkoutKit type to build.

## The iPhone app

In the repo under `ios/` *(my call)*. It's SwiftUI, built for iOS 17, and the project is generated with XcodeGen from a checked-in `project.yml`.

- **First launch:** a small settings screen asks for the LockedIn address and the watch key. They're stored in the iPhone's Keychain. The same settings screen can be reached later from a gear button.
- **Main screen:** the runs from the feed, grouped by day ("Today", "Tomorrow", "Thu 30 Oct"), each with its title, summary and an "optional" mark. Pull to refresh; it refreshes on open as well.
- **Swims** are listed too, with the swim's note under the summary, so the set can be read at the pool.
- **Tap a run or swim:**
  - For a run, the app builds a `CustomWorkout` from `workout`.
  - For a swim, it builds a `SingleGoalWorkout(activity: .swimming, swimmingLocation: .pool, goal:)`.
  - Either way it then opens `.workoutPreview`, and Apple's sheet takes it from there.
- **Errors** are shown in words: no connection, a wrong key (401), the server being down, or a run the app can't build. A single bad run doesn't hide the others.
- There's no watch target and no `WorkoutScheduler` in this version.

**Reinstalling:** `make ios` (or a script under `ios/`) regenerates the project and builds it signed with the owner's Personal Team (`-allowProvisioningUpdates`). It installs it on the plugged-in iPhone with `xcrun devicectl` and launches it. It uses `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`, because `xcode-select` points at the Command Line Tools. The team ID is read from the environment or a git-ignored local file, not committed *(my call)*. The README gains a section: setup, the weekly reinstall, the watch key on Vercel.

## Later (not now)

With a newer watch: add a watch app target and `WorkoutScheduler`, so the next 7 days sync to the watch by themselves, and the phone app becomes a status screen. Swims gain steps like runs, with `poolSwimDistanceWithTime` goals. The feed and the step model stay as they are.
