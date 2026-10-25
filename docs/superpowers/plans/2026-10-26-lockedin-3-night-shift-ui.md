# LockedIn Plan 3 — Night Shift UI, Body Check-ins & Reminders

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the web app in the "Night Shift" design the owner picked, with every page from the prototype and its small animations. Body becomes a single check-in form. Reminders ship as a calendar file plus "due" cards on the overview.

**Architecture:**
- **Backend:**
  - One migration: reminder settings on `profile`.
  - Two check-in routes: batch-save and history.
  - A route that returns an `.ics` calendar file.
  - Two due flags on `/api/overview`.
- **Frontend:**
  - Same React app, re-themed: dark tokens, Barlow Condensed + Inter, a CSS animation kit that respects `prefers-reduced-motion`.
  - Navigation: sidebar on desktop, tab bar on phones.
  - Pages are rebuilt one by one against the existing API.

**Design source (binding for look and behaviour):** canvas https://claude.ai/artifact/So5GaLVAiJZU3CxzHKeyq1, the "B · Night Shift — desktop prototype" row and "B · Night Shift" phone screens. Spec: `docs/superpowers/specs/2026-10-25-lockedin-design.md` (anti-goals still apply).

## Global Constraints

- **Unchanged from Plans 1–2:** owner-only routes, RLS on new tables/columns, UTC storage, Brussels weeks, metric units, no Strava, commit trailer.
- **Palette:** ground `#0f1011`, surface `#17191b`, raised `#1e2124`, line `#26292c`. Ink `#f2f2ee` / `#dcddd8` / `#b6b8b3`, muted `#8b8e88`. Accent lime `#c8f169`, accent ink `#0f1011`.
- **Sport colours:** bike `#4d97ec`, run `#ff7a45`, swim `#3ccf9a`, gym `#f0b429`, other `#8b8e88`. HR series `#ff6b6b`.
- **Fonts:** Barlow Condensed 600/700 for headings and big numbers (uppercase, letter-spaced headings); Inter 400–600 for body.
- **Animation kit:**
  - `rise` (fade-up 0.5 s, staggered by inline `animation-delay`)
  - `grow-y` / `grow-x` (bars)
  - `draw` (SVG lines)
  - `pop`, `pulse` (sync dot / due dot)
  - `lift` hover, row hover
  - All disabled under `prefers-reduced-motion: reduce`. Recharts `isAnimationActive` follows the same media query.
- **Tone:** no red for declines. Only "low" muscles, PRs and actions use the lime accent.
- **Accessibility:** real `<button>`/`<a>`/`<label>`, text contrast ≥4.5:1 on its surface, status never colour-only.
- **Layout:** works at 375 px. Sidebar ≥ 900 px wide, bottom tab bar below.

## Review Focus

1. **Check-in on a date that already has values.** Saving again replaces those types for that date, never duplicates. Blank fields are skipped, and an empty check-in → 422. Test in Task 1.
2. **Calendar file correctness.** Valid `VCALENDAR` with CRLF line endings, `RRULE:FREQ=WEEKLY;INTERVAL=n`, Europe/Brussels start at 09:00 on the next due date, a link to `/body`. The Hevy line is included only when enabled. Test in Task 1.
3. **Due logic.** Check-in is due when there are no measurements, or the last check-in date + interval ≤ today (Brussels). Hevy is due when it has never been uploaded or the last upload is ≥ 7 days ago. Test in Task 1.
4. **Reduced motion.** With `prefers-reduced-motion: reduce`, no CSS animation runs and the count-up shows the final number immediately. Verified in the browser in Task 8.
5. **Phone width.** Every page at 375 px: no horizontal page scroll, the tab bar never covers the last content. Verified in Task 8.

---

### Task 1: Backend — check-ins, reminder settings, calendar file, due flags

**Files:**
- Create: `supabase/migrations/20261026000002_reminders.sql`, `lockedin/routes/checkins.py`, `lockedin/reminders.py`
- Modify: `lockedin/routes/body.py` (profile fields), `lockedin/routes/overview.py`, `lockedin/app.py`
- Test: `tests/test_checkins.py`, `tests/test_reminders.py`

**Interfaces:**
- **Migration:** `alter table profile add column reminder_weeks smallint not null default 2 check (reminder_weeks in (1,2,4)), add column reminder_hevy boolean not null default true;`
- **Profile:** `GET/PUT /api/profile` gain `reminder_weeks: Literal[1,2,4] = 2` and `reminder_hevy: bool = True`.
- **`POST /api/checkins`** with body `{"measured_on": date, "values": {"<type_id>": float}}`:
  - Values ≤ 0 or null are skipped. If nothing is left → 422 `"Fill in at least one measurement."`. An unknown type_id → 404.
  - For each type, existing rows with that `(type_id, measured_on)` are deleted and the new row is inserted.
  - Returns 201 `{"measured_on", "saved": n}`.
- **`GET /api/checkins`** → `[{"measured_on": date, "values": {"<type_id>": float}}]`, newest first, grouped by date.
- **`lockedin/reminders.py`:**
  - `next_checkin_due(conn, today: date) -> date`: the last measurement date + `reminder_weeks`×7, or `today` if there are none.
  - `checkin_due(conn, today) -> bool`: `next_checkin_due <= today`.
  - `hevy_due(conn, now) -> tuple[bool, datetime | None]`: `(last hevy import_log.at is None or now − at ≥ 7 days, at)`.
  - `calendar_ics(conn, today: date, app_url: str) -> str`.
- **Calendar file:**
  - Content: `BEGIN:VCALENDAR`, `VERSION:2.0`, `PRODID:-//LockedIn//EN`, one `VEVENT`:
    - `UID:lockedin-checkin@lockedin`
    - `DTSTAMP` (UTC)
    - `DTSTART;TZID=Europe/Brussels:<next due>T090000`
    - `DURATION:PT15M`
    - `RRULE:FREQ=WEEKLY;INTERVAL=<weeks>`
    - `SUMMARY:LockedIn check-in`
    - `DESCRIPTION:` "Fill in your body measurements." + (if hevy) `\nUpload your latest Hevy export.`
    - `URL:<app_url>/body`
    - `VALARM` (`ACTION:DISPLAY`, `TRIGGER:PT0M`)
  - Lines joined with `\r\n`; text values escaped (`,` `;` `\`).
- **`GET /api/reminders/calendar.ics`:** owner-only, `text/calendar; charset=utf-8`, `Content-Disposition: attachment; filename="lockedin-checkin.ics"`. `app_url` is taken from the request's `Origin`/`Host` header (`https://<host>`); in tests the host is `testserver`.
- **`/api/overview`** gains `"checkin_due": bool`, `"next_checkin_on": date`, `"hevy_due": bool`, `"hevy_last_upload_at": datetime | null`, and keeps `measure_due` as an alias of `checkin_due`.

- [ ] **Step 1: Write failing tests:**
  - **Batch save:** saves 3 of 9 with blanks skipped. Re-saving the same date replaces values (count unchanged, new value). An empty body → 422. An unknown type → 404.
  - **History:** grouped newest first.
  - **Profile:** reminder fields round-trip; `reminder_weeks=3` → 422.
  - **`next_checkin_due`:** no data → today. Last measurement 2026-10-12 with 2 weeks → 2026-10-26 (due on 26 Oct). With 4 weeks → 2026-11-09.
  - **`hevy_due`:** never uploaded → True. Uploaded 2 days ago → False. 8 days ago → True.
  - **Calendar file:** contains `RRULE:FREQ=WEEKLY;INTERVAL=2`, `DTSTART;TZID=Europe/Brussels:20261026T090000` (today when there's no data), `URL:https://testserver/body`, every line ends in `\r\n`, and the Hevy line is absent when `reminder_hevy=false`.
  - **Overview flags** present.
  - All routes 401 without a token.
- [ ] **Step 2–4:** RED → implement → GREEN (`make test`).
- [ ] **Step 5: Commit** `feat: body check-ins, reminder settings, calendar file and due flags`.

### Task 2: Frontend foundation — theme, fonts, animation kit, shell

**Files:**
- Modify: `web/index.html` (Google Fonts link, `theme-color` `#0f1011`), `web/src/styles.css` (rewrite to the Night Shift tokens and the animation kit), `web/src/components/Layout.tsx` (sidebar ≥ 900 px with brand, 5 links, pulsing sync status from `/api/status`, sign out; tab bar below 900 px)
- Create:
  - `web/src/lib/motion.ts`: `prefersReducedMotion(): boolean`, `useCountUp(target: number, ms = 900): number` (ease-out cubic; returns `target` immediately when reduced motion is on), `stagger(i, base = 0.05, step = 0.04): CSSProperties`
  - `web/src/components/ui.tsx`: `Card`, `SectionTitle`, `Tile`, `Segmented` (`role="group"`, `aria-pressed`), `Chip`, `PageHeader` (eyebrow + uppercase H1 + optional right slot)
- Test: `web/src/lib/motion.test.ts`, checking `stagger(2)` → `{ animationDelay: "0.13s" }` and the count-up easing helper `easeOutCubic(0.5) ≈ 0.875`.

- [ ] RED → implement → GREEN (`npm --prefix web test -- --run`, `npm --prefix web run build`).
- [ ] **Commit** `feat(web): Night Shift theme, animation kit and app shell`.

### Task 3: Overview

Rebuild `web/src/pages/Overview.tsx`, `FocusCard`, `WinsStrip` and `WeeklyVolumeChart` to match the prototype:
- **Header:** eyebrow date + week number, H1 "Overview" (or "Welcome"/"Welcome back" + comeback card), and a Week/Month segmented control.
- **Hero row:** total (count-up) plus Bike, Gym (and Run/Swim when > 0) and Streak tiles; the sport tiles link to Trends.
- **Focus + new bests:** focus card with numbered items (01/02/03) beside the new-bests list, which links to the activity.
- **Stalled lately** card.
- **Weekly chart:** bars grow in; legend, tooltip, 12/26 toggle and table toggle kept.
- **Due cards:** the check-in due card (pulsing dot) → /body, and the Hevy card → /import, shown when `hevy_due` or always as a "last uploaded …" status.
- [ ] Type-check, build and test pass → **Commit** `feat(web): Night Shift overview`.

### Task 4: Activities and activity detail

- **Activities:** table-like rows (date · activity · time · distance · key metric · TSS) with row hover, a filter chip row including "Walks & duplicates", and Load more.
- **Ride/run detail:**
  - Header with sport eyebrow, title and date; a PR badge when a win for this activity exists (from `/api/overview` wins) — or skip if not available. Ruling allowed.
  - Tile grid; stacked power/HR/cadence (or pace/HR) charts sharing one hover cursor (Recharts `syncId`).
  - An effort note with a "Set FTP" link when FTP is estimated.
  - Watch-duplicate / HR-merge notes kept.
- **Gym detail:** exercise cards in a 2-column grid, set rows with an e1RM bar per set (`grow-x`), and the W/F/D/BW legend.
- [ ] Build → **Commit** `feat(web): Night Shift activities and details`.

### Task 5: Trends

- **Tabs:** segmented Bike · Run · Swim · Gym.
- **Bike:** FTP tile ("estimated" + link when no override), best 20-min tile with the delta, effort mix as a single segmented bar with labels, a "Try this" card, and three per-ride charts with dots.
- **Run:** the same pattern (pace reversed, aerobic efficiency, weekly km).
- **Swim:** weekly metres + pace.
- **Run/Swim empty states:** the ghost charts (shimmer) plus a "Check sync status" link to /import.
- **Gym:**
  - Muscle coverage rows (bar `grow-x` + target band, status text, inline "Add …").
  - Progress card with an exercise picker (all exercises, most recent first) and a line with dots and value labels.
  - Weekly volume bars.
  - "Tag your exercises".
- **Error and loading states** from Plan 2 kept.
- [ ] Build → **Commit** `feat(web): Night Shift trends`.

### Task 6: Body — check-in, history, reminders, profile

- **Check-in card:**
  - A date input (default today in Brussels).
  - One field per measurement type (all types from `/api/measurement-types`, in order). Each field shows its unit, a "last X" hint and a tip.
  - Tip text by name for the 9 defaults (from the prototype); custom types get no tip.
  - A filled-count progress bar, and Save → `POST /api/checkins` → "Saved" state, with history and the overview refreshed.
- **History table:** dates × types, with the change vs the previous check-in. It scrolls horizontally inside its card.
- **Reminder card:**
  - A 1/2/4-week segmented control and an "Also remind me to upload my Hevy export" checkbox; both save to the profile.
  - **Add to calendar:** `apiFetch` the `.ics` as a blob → object URL → download `lockedin-checkin.ics`, then a confirmation line.
- **Profile card:** as before, plus the reminder fields kept in sync.
- **"Measure the same way" card** with a "Track something else" form (existing POST /measurement-types).
- [ ] Build → **Commit** `feat(web): body check-ins, history and calendar reminders`.

### Task 7: Import and sign-in

- **Import:**
  - Three status tiles (Zwift / Apple Watch / Hevy) with a live dot when synced within 24 h, "Not set up" when the count is 0 for healthfit.
  - A dashed drop zone with a per-file progress row and result.
  - A Hevy card with result chips.
- **Sign in:** a big wordmark, a card form, a lime CTA, `placeholder` (no prefilled email), and the Supabase error message shown as before.
- [ ] Build → **Commit** `feat(web): Night Shift import and sign-in`.

### Task 8: Verify, docs, review

- [ ] Load the owner's real data into the local stack (as in Plan 2 Task 8).
- [ ] Drive every page with Playwright at 1440 px and 375 px. Check:
  - Check-in save → history row appears.
  - Calendar download returns `text/calendar`.
  - Filters, tabs and toggles work.
  - Reduced-motion run: no animations, the count-up shows its final value.
  - No console errors, no horizontal overflow.
- [ ] Update the README: Body check-in, reminders, and the deploy order (`supabase db push` before `git push`).
- [ ] Run the full test suites and the build → **Commit** `docs: check-ins and reminders`.
