# LockedIn: Agenda (week planner) with Zwift workouts

**Status:** designed in conversation on 2026-10-26. The owner approved the mockups ("looks good"). The details marked as my calls are mine; the owner has repeatedly asked me to "make it how you think is best".
**Builds on:**
- the coach: tools, approval-before-write, mid-conversation context
- the workout planner: routines from Hevy titles, `/plan`
- the Mac sync: `sync/fit_sync.py`, launchd
- the counted-session rules

## Why

The owner talks a week through with the AI coach, then wants it on a calendar: "alright change my agenda so that i can see it in there when to do what". Today the coach hands over Zwift workouts as XML to save by hand. The owner wants those to land in Zwift automatically. Sessions should tick off by themselves when the ride or Hevy workout comes in. The owner must be able to change the agenda themselves too, not only through the coach.

## Goals

### The Agenda page (`/agenda`)

- **Layout:** a Monday–Sunday week, Brussels time.
  - **Desktop (≥ 900 px):** seven day columns.
  - **Phone:** one row per day.
  - **Today** is highlighted. The week is in the URL (`?week=YYYY-MM-DD`), with ‹ › arrows.
  - A legend for the sport colours (`--sport-*`, plus a neutral colour for rest).
- **Items** show:
  - the title
  - a short summary: duration and power targets in W for Zwift workouts (from the current FTP), or the note
  - **Optional** as a dashed tag
  - **In Zwift ✓** once the Mac sync has fetched the file, otherwise "Goes to Zwift at the next Mac sync"
  - **Done**, ticked automatically (see "Ticking off")
  - **Plan it →** for gym items with a routine, linking to `/plan?day=<routine>`
- **Past days** show unticked items as plain "Not done". There's no red and no guilt wording.
- **Opening an item** shows:
  - for Zwift workouts, its shape as a small block chart
  - its details
  - edit controls: title, note, day, optional on/off, and delete (with confirm)
  - Moving or deleting a Zwift workout updates or removes its Zwift file at the next sync.
- **+ Add** on each day opens an add form:
  - **sport:** gym (pick one of the Hevy routines from the planner), run, swim, Zwift ride as a note only, rest, or other
  - **title** (prefilled for gym and rest), an optional note, and optional on/off
  - Structured Zwift workouts with power targets come from the coach; the form says so.
- **"Plan with coach"** button: opens the Coach page.

### The Overview

A **Today** card at the top lists today's items (title, summary, Zwift status). Gym items link to the planner. It's hidden when nothing is planned today.

### Navigation

- **Sidebar:** "Agenda" is the second item, after Overview.
- **Phone tab bar:** Home, Agenda, Coach, Activities, Muscles, More. **More** opens a small menu with Trends, Body and Import. The bar must stay at 6 columns with no overflow at 375 px.

### The coach

- **New tool `get_agenda {from, to}`:** returns the items in a date range (default: this week and next) with done state.
- **New tool `save_agenda {changes: [...]}`:** add, update (any field, including the day) or delete items.
  - Like `save_goal`, the system prompt says to use it only after the owner has agreed to the exact plan or change in this conversation.
  - The tool result lists what changed, so the coach can confirm it in chat.
- **Zwift workouts from the coach** are structured, not XML. An item can carry `zwift.blocks`, a list of:
  - `warmup` / `cooldown` `{duration_s, power_low, power_high}`
  - `steady` `{duration_s, power}`
  - `intervals` `{repeat, on_s, off_s, on_power, off_power}`
  - `free` `{duration_s}`

  Powers are fractions of FTP (0.3–1.6). `duration_s` is 10 s–4 h. There are at most 30 blocks, the total is at most 6 h, and `repeat` is 1–30. The server validates the blocks and builds the `.zwo` itself.
- **Prompt:**
  - The coach should put Zwift sessions in the agenda as structured workouts instead of pasting XML.
  - It shouldn't put the date into titles; the file name does that.
- **The turn context** includes today's and tomorrow's agenda items, so the coach knows what's planned.
- **Tool input validation** must handle nested arrays and objects, numbers and booleans (the current validator handles flat objects only).

### Zwift files (via the Mac sync)

- **Content:** the server renders each Zwift item with blocks as a ZWO workout:
  - `<author>LockedIn</author>`
  - `<name>YYYY-MM-DD Title</name>`
  - `<description>` from the note
  - `<sportType>bike</sportType>`
  - blocks mapped to `Warmup`, `Cooldown`, `SteadyState`, `IntervalsT` and `FreeRide`
  - all text XML-escaped
- **File name:** `YYYY-MM-DD <Title>.zwo`, with characters that aren't safe in file names replaced.
- **Scope:** only items dated today or later (Brussels) are served, so finished days don't pile up in Zwift.
- **Sync endpoint:** `POST /api/agenda/zwift/sync`, sync token only. It returns `[{item_id, filename, content}]` and records `zwift_synced_at` on each served item (that's what drives "In Zwift ✓").
- **The Mac sync script, after uploading:**
  - It calls that endpoint and writes the files into the Zwift workouts folder: `ZWIFT_WORKOUTS_DIR`, defaulting to the single numeric subfolder of `~/Documents/Zwift/Workouts/`. If there's none or more than one, it warns and skips.
  - It keeps a manifest, `.lockedin-workouts.json` in that folder, listing the files it wrote.
  - It deletes only manifest-listed files that are no longer served. It never touches any other file. It only rewrites a file when the content changed.
  - Errors in this step are logged and never block FIT uploads.
- **Sync interval:** the launchd fallback drops from 1 h to 15 min, so a plan agreed in chat reaches Zwift soon. The folder watch stays.
- **Zwift needs a restart** to see new custom workouts. The page says so once, near the Zwift status.

### Ticking off

This is computed on read; nothing is stored.

- **Matching:** for each item on day D (Brussels), find a counted activity on D:
  - **gym:** a Hevy workout whose title equals the item's routine. Without a routine, any gym session that day.
  - **Zwift / bike:** a counted bike activity (Zwift or Watch).
  - **run / swim:** a counted activity of that sport.
  - **rest / other:** never ticked.
- **Each activity ticks at most one item,** in item order. A ticked item links to the activity.

## Non-goals

- Recurring events, reminders or notifications, and calendar export for the agenda (the body check-in .ics stays as it is).
- Drag-and-drop between days (the day picker in the item sheet covers moving).
- Reading Zwift's own calendar or training plans.
- Agenda items generated by rules. The coach or the owner makes them.

## Anti-goals

- **Guilt:** red, streak-shaming, or "missed" counts for unticked sessions.
- **Touching Zwift files the app didn't write.**
- **The coach writing to the agenda without explicit agreement.**

## Constraints

- **Data:**
  - A new table `agenda_items`:
    - `id`, `day date not null`
    - `sport text check in ('gym','bike','run','swim','rest','other')`
    - `title text not null` (≤ 80 chars), `note text` (≤ 500)
    - `optional boolean default false`
    - `routine text` (gym), `zwift jsonb` (blocks)
    - `zwift_synced_at timestamptz`, `sort smallint default 0`
    - `source text check in ('coach','manual')`
    - `created_at`, `updated_at`
  - RLS and revokes like every table. The coach's read-only SQL may read it: grant and `coach_read` policy.
- **API (owner-only):**
  - `GET /api/agenda?week=` returns `{week_start, today, items: [...]}`, each with `done` and `activity_id`, Zwift summary watts and status.
  - `POST /api/agenda`, `PATCH /api/agenda/{id}`, `DELETE /api/agenda/{id}`.
  - Validation errors are 422 with clear messages.
  - The sync endpoint uses the sync token only.
- **Watts:** FTP-relative powers are shown in watts using the same FTP the app uses elsewhere (`ftp_at`). If there's no FTP, show percentages.
- **The Mac sync stays standard-library Python 3.9.** New behaviour is covered in `tests/test_fit_sync.py` with the fake HTTP.
- **Style:** Night Shift, animation kit, reduced motion, 375 px with no overflow.

## Calls I made

- **Tab name and place:** "Agenda", second in the menu.
- **Phone "More" menu:** Trends, Body and Import move into it.
- **Ticking rules** as above.
- **Zwift scope:** only today-and-later Zwift files, with a manifest, written into the single Zwift ID folder.
- **Sync interval:** 15 minutes.
- **Structured blocks** instead of XML from the model.
- **`zwift_synced_at`** as the "In Zwift ✓" signal.
- **Prompt:** dates in file names, not titles.
- **Overview:** the Today card.
