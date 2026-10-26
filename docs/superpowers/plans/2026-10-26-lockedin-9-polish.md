# LockedIn Plan 9: Fix the Deferred Minors

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fix every minor finding that the final reviews of Plans 4–8 deferred (owner: "fix all what has to be fixed now"). Each fix gets a test that fails first wherever one can be written, and the test name goes in the ledger.

**Specs:** the specs of Plans 4–8 (`docs/superpowers/specs/2026-10-2*-lockedin-*.md`). This plan adds no new behaviour beyond what they say, apart from the small additions named below.

## Global Constraints

- No guilt wording.
- Night Shift style; reduced motion respected; 375 px with no overflow.
- The Mac sync stays standard-library Python 3.9.
- Migrations are additive only. Plan 8's migrations aren't deployed yet, but new changes still go in new files.

## Review Focus

1. Every fix keeps the earlier features' tests green.
2. Coach changes must keep stored conversations replayable: no edits to history, and anything the model sees must stay append-only.
3. Mac sync changes must still never touch a file the script didn't write.
4. Frontend fixes must not reintroduce hook-order bugs; the real-router render tests stay.
5. Performance fixes must return exactly the same data (same tests).

---

### Task 1: Coach

- [ ] **SQL result size:** `coach.run_query` caps its result at 1 MB and raises "Result too large; select fewer or shorter columns". Test: `select repeat('x', 2000000)` → `QueryRejected` with that message.
- [ ] **Advisory locks:** call `pg_advisory_unlock_all()` before the SQL connection is returned. Test: a query taking `pg_advisory_lock(42)` leaves no lock (`pg_locks`).
- [ ] **Migration** (`coach.run_query`):
  - `set search_path = public, pg_temp`
  - `set app.settings.jwt_secret = ''`, so `current_setting` can't read the local secret
  - Test: `select current_setting('app.settings.jwt_secret', true)` returns empty or null.
- [ ] **Capped final round:** the call after the tool cap sends `tool_choice: {"type": "none"}` (allowed on Opus 5.5). The `CoachLLM.stream` signature gains `tool_choice`. Test: FakeLLM records `tool_choice == {"type": "none"}` on the last call.
- [ ] **Unparseable-JSON retry:** emit `{"type": "reset"}`, and the page drops that round's partial text. Tests: loop + a `sse` / Coach page handler unit test.
- [ ] **`GET /api/coach/status`** returns `{ready: bool, model}`. The Coach page shows the setup message on load when it isn't ready. Tests: route + Coach page.
- [ ] **`postStream` on 401:** signs out and redirects like `apiFetch`. Test: vitest with a 401 fetch mock.
- [ ] **Context-limit message:** a 400 whose message mentions the prompt being too long (context) → "This chat got too long; start a new one." Test: adapter with an `APIStatusError` 400 "prompt is too long".
- [ ] **README:** `ANTHROPIC_MODEL` must be a model that supports mid-conversation system messages and `fallbacks: "default"` (Opus 5.5 / Opus 5 / Fable 5.1).
- [ ] **Coach `SCHEMA_TEXT`:** document `agenda_items.targets`, `goal_id` and the `goals.area` values. Test: the text contains them.

### Task 2: Muscle map

- [ ] **Week navigation:** derive ‹/› from the URL week, and ignore stale responses. Test: page test where two quick clicks request two different weeks.
- [ ] **Main lift:** one batched query for all muscles' main lifts. Test: same results (existing tests), plus a query-count check under 15 statements for `muscle_map`.
- [ ] **Week lower bound:** `?week=` before 2000-01-01 is treated as the first week, or the current week if there's none. Test: `week=0001-01-03` → 200.
- [ ] **Coach composer offset:** match the tab-bar height via a CSS variable `--tabbar-h`, used by both.
- [ ] **Touch:** a tap (`pointerType` touch) doesn't open the floating panel. Test: page test with `pointerType` "touch".
- [ ] **Tests:** add the spring DST week (2027-03-28) and "history's last bar equals sets".

### Task 3: Planner and goals

- [ ] **`goal_for`:** require word boundaries. Reject the loose match when the exercise's base name appears in the goal text only as part of a longer known exercise name ("incline bench press" vs "bench press"). Tests: "Incline bench press 40 kg dumbbells" → not Bench Press (Barbell); "Bulgarian split squat" → not Squat; "Romanian deadlift 100" → not Deadlift.
- [ ] **Plan freshness:** include the comeback state. A plan built under a different comeback state is rebuilt. Test.
- [ ] **`never` on a stale plan:** refresh `prefs_hash` only if it matched before. Otherwise rebuild. Test.
- [ ] **`/plan` with no history at all:** no "Welcome back" (use `comeback.days_since is None`). An empty "missed" plan shows an empty-state line. Tests.
- [ ] **Preferences opened from the "missed" plan:** return to it. Hide Swap on items without a muscle. A 404 on an item action reloads the plan. Page tests.
- [ ] **⋯ menu:** arrow keys move between items; choosing returns focus to the ⋯ button. Page test.
- [ ] **Overview goals card:** shows "Couldn't load goals" on error. The Preferences panel shows an error when muscles fail to load. Tests.
- [ ] **Never-suggest list:** the `never` route caps it at 200, dropping the oldest. Test.
- [ ] **`save_goal` with `exercise`:** must be a known exercise (logged or in the library). Otherwise error listing close matches (difflib). Test.
- [ ] **`goal_muscles`:** only for gym/general goals; logged names computed once per call. Tests (body goal "Chest 105 cm" doesn't tag chest).

### Task 4: Agenda and sync

- [ ] **Agenda page:** reset `error` on week change; derive ‹/› from the URL; ignore stale responses. Page test.
- [ ] **422 messages:** strip "Value error, " (`RequestValidationError` handler for agenda routes). Test: a blank title → message without the prefix.
- [ ] **Control characters:** strip them from title and note (except tab and newline in notes). Test: a title with `\x07` saved without it; ZWO parses.
- [ ] **`save_agenda`:** cap at 30 changes server-side; reject a boolean id. Tests.
- [ ] **Add sheet:** switching away from gym clears a title that was the routine name. Page test.
- [ ] **Focus:** the More menu returns focus to its button on Escape and closes on selecting the current page. The sheet returns focus to the opener. Tests.
- [ ] **`turn_context`:** wrap the agenda lines; on error, "Agenda: unavailable right now." Test.
- [ ] **File names:** transliterate non-ASCII ("Vélo" → "Velo") before replacing. Test.
- [ ] **Sync manifest:** mark a LockedIn file the owner edited as `"released"`, so later runs skip it silently. Test: the second run has no warning.

### Task 5: Session pages and Today

- [ ] **Goal lift `ready`:** judged on the best 3 top-weight sets. Plan items get `goal_extra: true`. The gym ✓ accepts planned sets minus the goal extra. Tests.
- [ ] **Ridden coverage:** by time span (`min(end, t_last) − max(start, t_first)`), not sample count. Test with 3 s sampling.
- [ ] **Splits:**
  - Use moving time: only add time when speed > 0.5 m/s, if there's a speed stream.
  - Interpolate across distance jumps, so no absurd splits.
  - Tests: a 60 s stop doesn't slow the split; a 1.5 km jump gives no split under 120 s/km.
- [ ] **Session charts:**
  - y-axis values (W / pace / FTP) as HTML labels, readable at 375 px.
  - Hover readout: time, power and target.
  - `actual.series` reuses `routes/activities.downsample` for thinning.
  - Page test for the axis labels.
- [ ] **Intervals tile:** shows "N of M on target" instead of comparing with the first target. Page test.
- [ ] **Overview "Next" line:** looks into the next week when needed (fetches `?week=` of tomorrow on Sunday). Test.
- [ ] **Agenda:** shows the goal tag on done items too.
- [ ] **Overview Today:** says "Couldn't load today's plan" on error. Test.
- [ ] **Gym rows:**
  - Handle the same exercise planned twice: match by order, and use row keys with an index.
  - "What was planned" on a done gym day doesn't show "Plan it".
  - Tests.

### Task 6: Verify and review

- [ ] Run the full pytest, vitest and build.
- [ ] Playwright smoke at 1440 px and 375 px over Overview, Agenda, a session, Muscles, Plan and Coach: no console errors or overflow.
- [ ] Fresh final review, one fix pass, then report.

## Not fixed (rulings)

- **SSE heartbeat during long silences:** needs the stream to run on a separate thread. The loop already sends text and tool events as they come. Deferred to a later plan if the phone ever drops a long answer.
- **`net.*` functions readable by `coach_ro` on Supabase:** read-only and no outbound path (`http_get` denied). Revoking would touch Supabase's own grants.
- **Zwift folder writes when Zwift's cloud sync restores files:** can't be tested from here.
