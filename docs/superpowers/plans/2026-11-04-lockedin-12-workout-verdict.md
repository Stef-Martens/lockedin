# The coach's verdict on the last workout: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The dashboard shows, unasked, a short saved verdict from the coach on the latest workout: how it went and how on point it was against the plan.

**Architecture:**
- **New package `lockedin/verdict/`:** `store.py` (the table and the one-paid-call claim), `facts.py` (what the model is told, including run results per planned step), `write.py` (the one model call).
- **`routes/verdicts.py`** ties them together: short transactions, no connection held during the model call.
- **Web:** one `VerdictCard` component used on the Overview, session and activity pages.

**Tech Stack:** FastAPI + SQLAlchemy `text()`, Supabase migrations, `anthropic` SDK 2.3.0 (beta messages, `output_config.format`), pytest; React 18 + Vitest.

**Spec:** [docs/superpowers/specs/2026-11-04-lockedin-workout-verdict-design.md](../specs/2026-11-04-lockedin-workout-verdict-design.md)

## Global Constraints

- **No worktrees.** Work directly on `main`; commit per task; don't push, don't run `supabase db push` (the owner decides; the migration goes first).
- **Local DB:** apply the new migration with `supabase migration up --local`.
- **Labels:** `on_plan`, `close`, `off_plan`, `unplanned`, shown as `On plan`, `Close to plan`, `Off plan`, `Not planned`. The model chooses from the first three; the server sets `unplanned`.
- **Statuses:** `done`, `writing`, `over_budget`, `failed`, `none`.
- **Windows:** new verdicts only for workouts up to 14 days old; no dashboard card past 14 days; a claim is abandoned after 6 minutes; after a failure, no new attempt for 15 minutes.
- **The polling page:** every 3 seconds, at most 90 seconds.
- **Facts:** only numbers present in the facts may be used; no raw chart series go to the model.
- **Costs:** every call is recorded with `usage.record(conn, None, calls, now)` and checked against `settings.coach_daily_budget_usd` with `usage.spent_today`.
- **Copy:** plain words, as in the spec's States section.

## Review Focus

1. **Two tabs, or React's double effect, open the dashboard at the same moment:** exactly one model call; the other request sees `writing` (Task 4 test).
2. **The function dies during the call:** the claim is free again after 6 minutes, and not before (Task 1 test).
3. **The model refuses, returns broken JSON, or the API is down:** `failed`, the dashboard unaffected, no retry within 15 minutes (Task 3 and 4 tests).
4. **A workout on a rest day, or a walk, or a superseded copy:** rest counts as `unplanned`; a walk is never the last workout; a superseded id gives 404 (Task 1 and 4 tests).
5. **A run done without following its steps** (a free run on a day with intervals planned): no made-up per-step results (Task 2 test).

---

### Task 1: The table and the claim

**Files:**
- Create: `supabase/migrations/20261104000001_workout_verdicts.sql`, `lockedin/verdict/__init__.py`, `lockedin/verdict/store.py`
- Test: `tests/test_verdict_store.py`

**Interfaces:**
- Produces, in `lockedin/verdict/store.py`:
  - `latest_activity(conn, now) -> Row | None`: newest `start_at` passing `COUNTED_SQL`.
  - `counted_activity(conn, activity_id) -> Row | None`: the same filter for one id.
  - `ticking_item(conn, now, activity) -> dict | None`: the agenda item whose `activity_id` is this activity, from `items_between` over the activity's local day (`TZ`).
  - `is_plan(item) -> bool`: an item that isn't `rest`.
  - `read(conn, activity_id) -> Row | None`.
  - `up_to_date(row, item) -> bool`: false when `row.label == 'unplanned'` and `is_plan(item)`, or when `row.label` is another label and not `is_plan(item)`. Otherwise true, even if the item differs.
  - `claim(conn, activity_id, item_id, now) -> bool`: true when this caller may call the model. Atomic: a single `insert … on conflict (activity_id) do update … where` that returns a row only if there's no row yet, or the row isn't written and its claim is older than 6 minutes and its failure older than 15 minutes (or null). An out-of-date written verdict is also claimable; the route says so with a `rewrite: bool = False` argument.
  - `save(conn, activity_id, label, body, model, now)`, which clears `failed_at`; `fail(conn, activity_id, now)`, which sets `failed_at` and clears `claimed_at`.
  - `release(conn, activity_id)`: clears `claimed_at` without a failure, for over-budget checks that run after a claim.

- [ ] **Step 1: Write the failing tests:**
  - `test_latest_skips_walks_and_superseded`.
  - `test_claim_only_once`: the second `claim` returns False.
  - `test_claim_free_after_six_minutes`: False at 5:59, True at 6:01.
  - `test_failed_waits_fifteen_minutes`: after `fail`, False at 14:59, True at 15:01.
  - `test_written_not_claimable_without_rewrite`, and claimable with `rewrite=True`.
  - `test_up_to_date`: the four cases, plus a swapped item staying true.
  - `test_rest_item_is_not_a_plan`.
  - `test_ticking_item_uses_the_local_day`: a workout at 23:30 UTC on the Brussels next day.
  - `test_coach_cannot_read_verdicts`: `coach_ro` has no select (`has_table_privilege('coach_ro', 'workout_verdicts', 'select')` is false).
- [ ] **Step 2: Run them and check they fail.** `.venv/bin/python -m pytest tests/test_verdict_store.py -q`: an ImportError.
- [ ] **Step 3: Write the migration and the store.** Columns as in the spec; `item_id` references `agenda_items` with `on delete set null`; `label` check on the four labels; RLS on, `revoke all … from anon, authenticated`, no grant to `coach_ro`. Check `tests/test_schema.py` for a list of tables to extend. Apply with `supabase migration up --local`.
- [ ] **Step 4: Run them and check they pass.** The same command, then `tests/test_schema.py`.
- [ ] **Step 5: Commit** `feat(verdict): a saved verdict per workout, with a claim so it's only paid for once`.

### Task 2: What the model is told

**Files:**
- Create: `lockedin/verdict/facts.py`
- Modify: `lockedin/agenda/actual.py` (only to share the moving-time timeline that `splits` builds, as a helper)
- Test: `tests/test_verdict_facts.py`

**Interfaces:**
- Consumes: `ticking_item`, `is_plan` (Task 1); `detail(conn, now, item_id)`, `act.activity`, `act.streams`, `act.splits`, `act.zones`, `counted_sessions`, `active_goals`, `hr_zone_bounds`, `max_hr_at`.
- Produces:
  - `facts(conn, now, activity_id) -> dict`, JSON-safe, with keys `workout`, `plan` (null when none), `rest_day` (bool), `comparison`, `step_results` (null when not available), `recent` (up to 3), `easy_back`, `goals`.
  - `step_results(steps: dict, stream) -> list[dict] | None`.

- [ ] **Step 1: Write the failing tests:**
  - `test_planned_ride_has_parts`, `test_planned_run_has_splits_and_zones`, `test_gym_has_rows`.
  - `test_unplanned_run_has_no_plan`: `plan` null, with splits and zones still there.
  - `test_unplanned_gym_has_its_sets`.
  - `test_rest_day_is_flagged`: `plan` null, `rest_day` true.
  - `test_no_raw_series`: `json.dumps(facts(...))` holds no list longer than 100 items, and the keys `power`, `hr` and `pace` from `detail()`'s `actual` are gone.
  - `test_recent_is_same_sport_and_earlier`, at most 3, newest first.
  - **`step_results`:** a synthetic stream (1 sample per second, known speed per stretch) against `TEMPO`-like steps with time goals:
    - `test_steps_by_time`: each step (repeats unrolled) reports `kind`, its repeat number, planned goal, planned target, seconds, metres, pace s/km, average HR and `in_target` (true/false/null), with exact values.
    - `test_steps_by_distance`: distance goals end at the metres, not the seconds.
    - `test_pause_does_not_shift_steps`: a stopped stretch doesn't use up a step's time.
    - `test_open_goal_stops_matching`: steps up to the open one are reported, none after.
    - `test_free_run_gets_no_results`: a run that covers under 90 % of the planned time and distance before its open step gives `None`.
    - `test_no_stream_gets_no_results`.
- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.**
  - **Planned:** take `detail()`, drop `actual`'s series keys, and keep `parts`, `splits`, `zones`, `rows`, `intervals_on_target`.
  - **Unplanned:** build the same `actual` shape from `act.activity` and `act.streams`. For gym, reuse the set query the activity page uses (`lockedin/routes/activities.py`).
  - **Why `step_results` can be trusted:** the watch advances time and distance steps by itself, so from the start of the run the plan's order and lengths give each step's window on the moving-time timeline. Add a line `"matched_by": "the plan's order and lengths from the start of the run"` to the facts, so the model can say so if asked. Below the 90 % rule it returns `None` and the model has the km splits instead *(ruling: this is the spec's "small and exact" case)*.
- [ ] **Step 4: Run them and check they pass.** Also `tests/test_session_detail.py`, for the helper move.
- [ ] **Step 5: Commit** `feat(verdict): the facts about a workout, with a run's results per planned step`.

### Task 3: The one model call

**Files:**
- Create: `lockedin/verdict/write.py`
- Modify: `lockedin/coach/llm.py` (`CoachLLM.stream` and `AnthropicLLM.stream` gain `output_format: dict | None = None`), `tests/test_coach_loop.py` (`FakeLLM.stream` accepts it and records it; the adapter request-shape test)
- Test: `tests/test_verdict_write.py`

**Interfaces:**
- Produces, in `lockedin/verdict/write.py`:
  - `class VerdictFailed(Exception)`.
  - `write(llm: CoachLLM, facts: dict, planned: bool) -> Written`, a dataclass with `label: str`, `text: str`, `usage: list[dict]`.
  - `SYSTEM`, the prompt with the spec's rules and label meanings.
  - `SCHEMA`: an object with `label` (enum `on_plan`, `close`, `off_plan`) and `text`, both required, `additionalProperties: false`.
- The request sets `output_config.format = {"type": "json_schema", "schema": SCHEMA}` when `output_format` is given, merged with the existing `effort`. That shape comes from the SDK's `BetaOutputConfigParam` / `BetaJSONOutputFormatParam`; check the type in `.venv` and don't guess.

- [ ] **Step 1: Write the failing tests:**
  - `test_write_returns_label_and_text`: a `FakeLLM` returning a JSON text block.
  - `test_unplanned_overrides_the_label`: `planned=False` gives `unplanned` whatever the model said.
  - `test_sends_facts_and_no_tools`: `tools == []`, facts in the user message, schema passed.
  - `test_empty_text_fails`, `test_bad_json_fails`, `test_refusal_fails` (`stop_reason="refusal"`), `test_coach_unavailable_fails`: all raise `VerdictFailed`.
  - In `test_coach_loop.py`: the adapter test with `output_format` sets the `format` and keeps `effort`; without it the request is unchanged.
- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.** Collect the `Final` from `llm.stream`, ignoring text deltas. Read the text block from `Final.content`. A `FakeLLM` scripted turn's `Final` has no usage; `Written.usage` is then `[]`.
- [ ] **Step 4: Run them and check they pass.** Also `tests/test_routes_coach.py`, since the client's signature changed.
- [ ] **Step 5: Commit** `feat(verdict): one model call that returns a label and a few sentences`.

### Task 4: The API

**Files:**
- Create: `lockedin/routes/verdicts.py`
- Modify: `lockedin/app.py`
- Test: `tests/test_routes_verdicts.py`

**Interfaces:**
- Consumes: Tasks 1 to 3; `get_llm`, `get_coach_engine`, `get_now`, `get_settings`, `usage`.
- Produces: `GET /api/verdicts/latest` and `GET /api/verdicts/{activity_id}`, owner only, `Cache-Control: no-store`, returning:

```json
{"activity": {"id": 1, "sport": "run", "day": "2026-11-04", "start_at": "...", "title": "Tempo", "item_id": 7},
 "verdict": {"status": "done", "label": "on_plan", "text": "..."}}
```

`title` is the ticking item's title, else the sport's name. `item_id` is the ticking item, including a rest item, for the link. `label` and `text` appear only with `done`.

**The order of decisions:**
1. No counted activity → `{"activity": null}` on `latest`, 404 on the id route. On `latest`, an activity over 14 days old is also `{"activity": null}`.
2. A saved, up-to-date verdict → `done`.
3. Older than 14 days and nothing saved → `none`. Older with a saved verdict → `done`, without a rewrite.
4. No API key → `none`. Don't use `Depends(get_llm)`, which raises 503; build the client inside, through a small dependency tests can override.
5. Over budget → `over_budget`, with no claim taken.
6. `claim` false → `writing` if a claim is live, `failed` if the 15 minutes are running.
7. Claim true: leave the transaction, build the facts in a short one, call `write`, then save and record usage in a new one. Any exception → `fail` and `failed`, logged. Never a 500. Return `done`.

- [ ] **Step 1: Write the failing tests**, using `FakeLLM` and `client` as in `tests/test_routes_coach.py`:
  - `test_writes_once_then_serves_saved`: two GETs, one model call.
  - `test_concurrent_second_request_sees_writing`: a `FakeLLM` that, during its call, makes a second GET and asserts `writing`.
  - `test_records_usage_without_a_conversation`.
  - `test_over_budget`: no call, `over_budget`.
  - `test_no_key_is_none`, `test_old_workout_is_no_card`, `test_old_workout_page_is_none`, `test_old_saved_is_still_shown`.
  - `test_failure_is_failed_and_waits`: raises once; the second GET within 15 minutes makes no call.
  - `test_plan_added_later_rewrites`, `test_item_deleted_rewrites`, `test_target_edit_does_not_rewrite`, `test_second_workout_swap_does_not_rewrite`.
  - `test_rest_day_is_unplanned`, `test_superseded_is_404`, `test_requires_owner` (including the sync and watch tokens), `test_no_store`.
- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.** Use `get_coach_engine` for connections, as `routes/coach.py` does. Check the budget before claiming, with the budget and the claim in one short transaction.
- [ ] **Step 4: Run them and check they pass,** then the whole suite and `ruff check .`.
- [ ] **Step 5: Commit** `feat(verdict): the API behind the last workout's verdict`.

### Task 5: The card, the pages and the README

**Files:**
- Create: `web/src/components/VerdictCard.tsx`, `web/src/components/VerdictCard.test.tsx`
- Modify: `web/src/pages/Overview.tsx`, `web/src/pages/Overview.test.tsx`, `web/src/pages/Session.tsx`, `web/src/pages/Session.test.tsx`, `web/src/pages/ActivityDetail.tsx`, `README.md`

**Interfaces:**
- Consumes: the API in Task 4.
- Produces: `<VerdictCard source="latest" | activityId={n} />`. It loads by itself, separately from the page around it, so a slow or failed verdict never holds up or breaks that page.

- [ ] **Step 1: Write the failing tests** (fake timers, mocked `apiFetch`):
  - Each state from the spec's States section shows its exact copy.
  - `done` shows the label, text and the link: to `/agenda/{item_id}` when there's an item, else `/activities/{id}`.
  - `writing` checks again after 3 seconds and shows the result; it stops after 90 seconds, keeping the "being written" text.
  - Polling stops on unmount.
  - `{"activity": null}`, `none`, and a failed fetch render nothing.
  - On the session and activity pages, the header and link are left out, because the page already says what workout it is.
  - **Overview:** the card is above Today; the page's other content renders while the verdict's request is still pending.
- [ ] **Step 2: Run them and check they fail.** `npm --prefix web test -- --run`.
- [ ] **Step 3: Implement.**
  - Follow `Card`, `SectionHead` and the existing label and pill styles.
  - **Session page:** only on a done item, with `activityId={item.activity_id}`.
  - **Activity page:** always show it; for a ticked workout it's the same saved verdict *(ruling: simpler than hiding it, and costs nothing extra)*.
  - **README:** a short section under "6. Dashboard & focus suggestions": what the card shows, when it's written, what it costs, and that it counts towards the coach's budget.
- [ ] **Step 4: Run them and check they pass.** `npm --prefix web test -- --run && npm --prefix web run lint && npm --prefix web run build`, then the whole Python suite.
- [ ] **Step 5: Commit** `feat(web): the coach's verdict on the dashboard, session and activity pages`.
