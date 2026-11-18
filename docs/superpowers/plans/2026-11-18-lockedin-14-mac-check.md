# Mac check status and "Check again" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The site shows when the Mac last checked for workouts, and a "Check again" button makes the Mac nudge iCloud, rescan and report back.

**Architecture:** A one-row `mac_sync` table holds the last run and the latest request. The Mac reports every full run and polls once a minute (second launchd agent, `--poll`) for a request; the web reads it through `/api/status`.

**Tech Stack:** FastAPI + SQLAlchemy (Postgres/Supabase), stdlib-only Python on the Mac, React + vitest.

**Spec:** `docs/superpowers/specs/2026-11-18-lockedin-mac-check-design.md`

## Global Constraints

- `sync/fit_sync.py` stays standard library only (runs on the system `/usr/bin/python3` 3.9: no `match`, no `X | Y` at runtime outside annotations).
- The site never calls the Mac; only the Mac calls `/api/sync/mac/*` with the sync token.
- iCloud is restarted (`killall bird`) only when answering a request, never on a normal run.
- A failed report or poll never fails a sync run and a poll with nothing to do writes no log line.
- Stale thresholds: last check over **1 hour** → warning dot; `last_seen_at` over **3 minutes** → "hasn't been in touch".
- New table gets RLS on and no grants for `anon`/`authenticated`, like every other table.

## Review Focus

- Pressing twice while the first check runs: the second request must stay open, not be marked done by the first answer. (Task 1 test `test_newer_request_survives_older_answer`.)
- A poll arriving while a folder-change run holds the lock: it skips and leaves the request open for the next minute. (Task 2 test `test_poll_skips_when_locked`.)
- Mac never reported yet (fresh deploy, old agent still installed): header falls back to the old "Mac sync · <last workout>" text. (Task 4 test.)
- Network down during the poll: no exception, no log line, exit 0. (Task 2 test `test_poll_network_error_is_silent`.)
- No `HEALTHFIT_DIR` configured: the check still rescans, only the iCloud nudge is skipped. (Task 2 test `test_check_without_healthfit_skips_nudge`.)

---

### Task 1: Table, API and status

**Files:**
- Create: `supabase/migrations/20261118000001_mac_sync.sql`
- Create: `lockedin/routes/mac.py`
- Modify: `lockedin/app.py` (include both routers), `lockedin/routes/status.py` (add `mac`), `tests/test_schema.py` (add `"mac_sync"` to `TABLES`)
- Test: `tests/test_routes_mac.py`, `tests/test_routes_status.py`

**Interfaces:**
- Produces:
  - `POST /api/sync/mac/poll` (sync token) → `{"check_requested_at": str | null}`; sets `last_seen_at = now()`. Returns the request only when it is open (`check_requested_at` set and `check_done_at` null or older).
  - `POST /api/sync/mac/run` (sync token), body `{"uploaded": int>=0, "errors": int>=0, "answered": datetime | null}` → `{"ok": true}`. Sets `last_run_at`, `last_seen_at`, `last_run_uploaded`, `last_run_errors`; if `answered` equals the current `check_requested_at`, also sets `check_done_at = now()` and `check_uploaded = uploaded`.
  - `POST /api/sync/mac/check` (owner) → the `mac` object below; sets `check_requested_at = now()`.
  - `GET /api/status` gains `"mac": {"last_run_at", "last_seen_at", "last_run_uploaded", "last_run_errors", "check_requested_at", "check_done_at", "check_uploaded"}` (timestamps ISO or null).

- [ ] **Step 1: Migration.** `mac_sync(id int primary key default 1 check (id = 1), last_run_at timestamptz, last_seen_at timestamptz, last_run_uploaded int, last_run_errors int, check_requested_at timestamptz, check_done_at timestamptz, check_uploaded int)`, insert the row `(1)`, enable RLS, revoke all from anon, authenticated. Add `mac_sync` to `REFERENCE_TABLES`? **No**: it's truncated per test, so `SEED_SQL` in `tests/conftest.py` gets `insert into mac_sync (id) values (1);`.

- [ ] **Step 2: Failing tests** in `tests/test_routes_mac.py`:
  - `test_status_mac_empty`: `/api/status` → `mac` all null.
  - `test_run_report_sets_checked`: POST `/run` `{"uploaded": 2, "errors": 0}` with `SYNC_HEADERS` → status `mac.last_run_at` and `last_seen_at` set, `last_run_uploaded == 2`.
  - `test_check_then_poll_then_answer`: owner POST `/check` → poll returns that `check_requested_at`; `/run` with `answered` = it and `uploaded: 1` → status `check_done_at` set, `check_uploaded == 1`; next poll returns `null`.
  - `test_newer_request_survives_older_answer`: check → poll (A) → check again (B) → run answering A → poll still returns B, `check_done_at` null.
  - `test_poll_sets_seen`: poll alone sets `last_seen_at`, leaves `last_run_at` null.
  - `test_auth`: `/poll` and `/run` with owner headers → 401; `/check` with `SYNC_HEADERS` → 401; all without headers → 401.
  - `test_run_rejects_negative`: `uploaded: -1` → 422.

- [ ] **Step 3: Run** `pytest tests/test_routes_mac.py -v` → fails (404s).

- [ ] **Step 4: Implement** `lockedin/routes/mac.py` with `sync_router = APIRouter(prefix="/api/sync/mac", dependencies=[Depends(require_sync)])` and `router` (owner) for `/check`; a `mac_status(conn) -> dict` helper used by `/check` and `status.py`. Comparison of `answered` happens in SQL (`check_requested_at = :answered`). Include both routers in `app.py`; update `TABLES` in `test_schema.py`.

- [ ] **Step 5: Run** `pytest tests/test_routes_mac.py tests/test_routes_status.py tests/test_schema.py -v` → PASS; then `pytest -q` → all pass.

- [ ] **Step 6: Commit** `feat(sync): the Mac's last check and a check request on the server`

### Task 2: Mac script: report, poll, check

**Files:**
- Modify: `sync/fit_sync.py`
- Test: `tests/test_fit_sync.py`

**Interfaces:**
- Consumes: Task 1 endpoints.
- Produces:
  - `report_run(cfg, reports: list[SyncReport], http, answered: str | None = None) -> None`: posts totals (sum of `uploaded`, sum of `len(errors)`) to `/api/sync/mac/run`; swallows every exception.
  - `nudge_icloud(folder: Path, run_cmd=subprocess.run, sleep=time.sleep) -> None`: `/usr/bin/brctl download <folder>`, then `/usr/bin/killall bird`, then `sleep(NUDGE_WAIT_S)` with `NUDGE_WAIT_S = 30`.
  - `poll(cfg, http, run_sync=run, nudge=nudge_icloud, lock=run_lock) -> list[SyncReport] | None`: None when there's no request, the lock is taken, or the network fails.
  - `run_lock() -> contextmanager yielding bool` (True if acquired): `fcntl.flock(LOCK_EX | LOCK_NB)` on `fit-sync.lock` next to the state file.
  - CLI: `--poll`. `main` takes the lock for normal runs too; a normal run that can't get it prints `"<stamp> skipped: another sync is running"`.

- [ ] **Step 1: Failing tests** (fake `http` recording calls, like the existing ones):
  - `test_run_reports_totals`: two reports (uploaded 1 and 2, one error) → one POST to `/api/sync/mac/run` with `{"uploaded": 3, "errors": 1, "answered": null}`.
  - `test_report_failure_never_raises`: `http` raising `OSError` → `report_run` returns None.
  - `test_poll_nothing_to_do`: poll response `{"check_requested_at": null}` → returns None, `run_sync` and `nudge` not called.
  - `test_poll_answers_request`: response with `"2026-11-18T22:30:00.123456+00:00"` and `HEALTHFIT_DIR` set → `nudge` called with that folder, `run_sync` called once, the `/run` POST carries `answered` equal to that string.
  - `test_check_without_healthfit_skips_nudge`: no `HEALTHFIT_DIR` → `nudge` not called, `run_sync` called.
  - `test_poll_skips_when_locked`: `lock` yields False → no HTTP call at all, returns None.
  - `test_poll_network_error_is_silent`: `http` raising `URLError` → None, `main(["--poll"])` prints nothing (capsys).
  - `test_nudge_icloud_commands`: fake `run_cmd` records `["/usr/bin/brctl", "download", str(folder)]` then `["/usr/bin/killall", "bird"]`; fake `sleep` gets 30.

- [ ] **Step 2: Run** `pytest tests/test_fit_sync.py -v` → new tests fail.

- [ ] **Step 3: Implement** as in Interfaces. `main` without `--poll`: under the lock, `run(...)`, print as today, then `report_run(cfg, reports, urllib_http)`. With `--poll`: `poll(...)`; if it returned reports, print them the same way, with `"(check from the site)"` appended to the first line. Update the module docstring.

- [ ] **Step 4: Run** `pytest tests/test_fit_sync.py -v` → PASS.

- [ ] **Step 5: Commit** `feat(sync): the Mac answers a check from the site and reports every run`

### Task 3: launchd poll agent

**Files:**
- Create: `sync/com.lockedin.fitsync.poll.plist.template` (Label `com.lockedin.fitsync.poll`, ProgramArguments `__PYTHON__ __SCRIPT__ --poll`, `StartInterval 60`, no `RunAtLoad`, same log)
- Modify: `sync/install.sh` (render and bootstrap both), `sync/uninstall.sh` (remove both)

- [ ] **Step 1:** Render the second template with the same Python helper (loop over both templates); bootout/bootstrap each label.
- [ ] **Step 2: Verify** `bash -n sync/install.sh sync/uninstall.sh` passes; render to a temp dir by running the Python snippet with a scratch `dst` and `plutil -lint` both outputs → `OK`.
- [ ] **Step 3: Commit** `feat(sync): a one-minute agent that picks up checks from the site`

### Task 4: Web: header line and "Your Mac" tile

**Files:**
- Modify: `web/src/lib/types.ts` (`MacStatus`, `Status.mac`), `web/src/components/Layout.tsx`, `web/src/pages/Import.tsx`, `web/src/styles.css` (`.sync-dot.stale`, amber)
- Test: `web/src/components/Layout.test.tsx`, `web/src/pages/Import.test.tsx`

**Interfaces:**
- Consumes: `/api/status` `mac`, `POST /api/sync/mac/check`.
- Produces: `MacStatus { last_run_at, last_seen_at, check_requested_at, check_done_at: string | null; last_run_uploaded, last_run_errors, check_uploaded: number | null }`.

- [ ] **Step 1: Failing tests.**
  - Layout: `mac.last_run_at` 4 min before now → text `Mac checked 4 min ago`; `mac` absent or `last_run_at` null → existing `Mac sync · 3 h ago` test still passes; `last_run_at` 2 h old → the dot has class `stale`.
  - Import: tile shows `Checked 4 min ago`; clicking **Check again** calls `apiFetch("/api/sync/mac/check", {method: "POST"})` and shows `Waiting for your Mac…`; when a later status has `check_done_at >= check_requested_at` and `check_uploaded: 1` → `Done · 1 new workout` (0 → `Done · nothing new`); `last_seen_at` 10 min old while waiting → text containing `hasn't been in touch since` and the local time `HH:MM`.

- [ ] **Step 2: Run** `cd web && npx vitest run src/components/Layout.test.tsx src/pages/Import.test.tsx` → fail.

- [ ] **Step 3: Implement.** Layout: `Mac checked {ago(last_run_at)}` when present, dot `stale` when older than 1 h, `live` when recent upload as today. Import: a fourth `StatusTile`-like card "Your Mac" with the button; after a press re-fetch `/api/status` every 5 s, stop after 5 min or when done. A request still open on page load also shows "Waiting for your Mac…" and polls.

- [ ] **Step 4: Run** `cd web && npx vitest run && npx tsc -b` → all pass.

- [ ] **Step 5: Commit** `feat(web): when the Mac last checked, and a button to check again`

### Task 5: README and deploy

**Files:** Modify `README.md` section 3 (two lines in the header, the button, the minute agent) and the deploy note.

- [ ] **Step 1:** Update README; commit `docs(sync): the Mac's check line and the Check again button`.
- [ ] **Step 2:** `supabase db push` (migration first), then `git push`.
- [ ] **Step 3:** Run `sync/install.sh`; `launchctl print gui/$(id -u)/com.lockedin.fitsync.poll` shows the agent; the main plist shows `StartInterval 900`; after a minute `/api/status` (via the site) shows `last_seen_at`.
