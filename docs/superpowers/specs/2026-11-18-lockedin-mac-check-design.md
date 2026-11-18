# Mac sync: "checked" status and a "Check again" button

## Why

On 18 Nov the site said "Mac sync · 13 days ago". The sync was running fine; iCloud on the Mac had stopped
pulling HealthFit's folder, so there was nothing new to upload. The label only shows when the last workout came
in, so "the Mac is off", "iCloud is stuck" and "nothing to upload" all look the same. What fixed it was asking
iCloud to refresh the folder and restarting the Mac's iCloud service (`bird`). The owner wants to see when the
Mac last looked, and a button to do that fix from the site, without a terminal.

## Goals

- The header and Import page say when the Mac last checked, next to when the last workout came in.
- A stale check (over an hour) is visible: the Mac is asleep, off, or the agent is broken.
- A "Check again" button on the Import page: the Mac nudges iCloud, rescans, uploads, and the page shows the
  outcome ("1 new workout" / "nothing new").
- If the Mac hasn't been in touch for a few minutes, the button says so instead of spinning.

## Non-goals

- The site never reaches into the Mac; the Mac only calls the site. No push, no open port.
- No restart of iCloud on normal runs, only when the button asks for it.
- No history of runs; only the latest run and the latest request.

## Approaches

1. **Mac polls for requests every minute** (picked). A second, tiny launchd job calls the site once a minute;
   when a check was requested it runs the iCloud nudge and a full sync and reports back. A press is answered
   within about a minute while the Mac is awake. Cost: one small request a minute (fine for Vercel and
   Supabase, and it keeps the free Supabase project awake).
2. **Requests picked up at the normal run** (every 15 min). Simplest, but a press can sit for 15 minutes and
   the button feels broken.
3. **Status line only, no button.** Shows the problem but leaves the fix to a terminal, which is what the
   owner asked to avoid.

## Design

- **Table `mac_sync`**, one row: `last_run_at`, `last_run_uploaded`, `last_run_errors`, `last_seen_at`,
  `check_requested_at`, `check_done_at`, `check_uploaded`.
- **API**
  - `POST /api/sync/mac/run` (sync token): the Mac reports a full run (uploaded, errors, and the request it
    answered, if any). Sets `last_run_at` and `last_seen_at`. A check is marked done only if the request it
    answered is still the current one, so a second press during a check isn't lost.
  - `POST /api/sync/mac/poll` (sync token): sets `last_seen_at`, returns the open request, if any.
  - `POST /api/sync/mac/check` (owner): records a new request.
  - `GET /api/status` gains `mac` with the fields above.
- **Mac (`sync/fit_sync.py`)**
  - Every full run ends by reporting to `/run`. A failed report never fails the run.
  - New `--poll` mode: one call to `/poll`. With no request it exits silently (no log line). With one it
    asks iCloud to download the HealthFit folder (`brctl download`), restarts `bird`, waits briefly, runs a
    normal full sync, and reports it as the answer.
  - Two runs at once (the poll's check and a folder-change run) are prevented with a lock file; the second one
    simply skips.
- **launchd:** a second agent `com.lockedin.fitsync.poll`, `StartInterval 60`, same Python, `--poll`.
  `install.sh` installs both (and re-installing switches the old hourly agent to 15 minutes); `uninstall.sh`
  removes both.
- **Web**
  - Header: "Mac checked 4 min ago" from `last_run_at`, falling back to the old "last workout" text until the
    Mac has reported once. The dot turns to a warning colour when the last check is over an hour old.
  - Import page: a "Your Mac" tile: last check, last workout, and the **Check again** button. After a press
    the page refreshes the status every few seconds: "Waiting for your Mac…", then "Done · 1 new workout" or
    "Done · nothing new". If `last_seen_at` is older than 3 minutes: "Your Mac hasn't been in touch since
    14:02. It'll check as soon as it wakes up."
- **README:** section 3 explains the two lines and the button; the deploy note says to run
  `supabase db push`, `git push`, then `sync/install.sh` once more.

## Left to the builder

Exact wording and layout of the tile, poll interval on the page (a few seconds, stop after ~5 minutes), how
long to wait after restarting `bird`.
