# LockedIn

A personal training tracker for one person. It collects:

- **Zwift rides** from the Mac where Zwift runs
- **Apple Watch runs, swims and other workouts** through the iPhone app HealthFit
- **Hevy gym workouts** from Hevy's CSV export

It also stores **body measurements** like weight, chest and arms. Everything is in one place you can open on your phone.

It runs on **Vercel** (the web app plus a Python API) and **Supabase** (Postgres plus login). A small script on your Mac uploads new ride and workout files automatically.

Coming next: an overview dashboard with "what to focus on" suggestions (plan 2) and an AI coach (plan 3). See `docs/superpowers/`.

---

## 1. Run it locally

You need Docker Desktop (running), the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started), Python 3.12+ and Node 20+.

```bash
make install                      # Python venv + web dependencies
cp .env.example .env              # then fill in the two keys below
supabase start                    # first run downloads the Docker images (a few minutes)
supabase status                   # copy "anon key" → VITE_SUPABASE_ANON_KEY, "service_role key" → SUPABASE_SERVICE_ROLE_KEY
supabase db reset                 # creates the tables
make owner EMAIL=you@example.com PASSWORD='choose-one'   # the only account; must match OWNER_EMAIL in .env
make dev                          # API on :8000, web app on http://127.0.0.1:5173
```

Run the tests with `make test`. It creates a separate `lockedin_test` database, so your local data is safe.

To try it without real data, sign in, open **Import**, and upload the files in `samples/`.

## 2. Hosted setup (Supabase + Vercel)

### Supabase

1. Create a project at [supabase.com](https://supabase.com). Pick region **Central EU (Frankfurt)**.
2. Link it and create the tables:
   ```bash
   supabase login
   supabase link --project-ref <your-project-ref>
   supabase db push
   ```
3. Turn off sign-ups: **Authentication → Sign In / Providers → Email**, then switch off **Allow new users to sign up**.
4. Create your account. This uses the hosted keys from **Project Settings → API Keys**:
   ```bash
   SUPABASE_URL=https://<ref>.supabase.co SUPABASE_SERVICE_ROLE_KEY=<service_role / secret key> \
     OWNER_EMAIL=you@example.com .venv/bin/python scripts/create_owner.py --email you@example.com --password '...'
   ```
5. Get the database URL: click **Connect** and copy the **Transaction pooler** string (port **6543**). Change `postgresql://` to `postgresql+psycopg://`.

Free projects **pause after about a week with no activity**. Your regular syncs should keep it awake. If it ever pauses, open the Supabase dashboard and click **Restore project**.

### Vercel

1. Push this repo to GitHub, then **Add New → Project** in Vercel and import it. `vercel.json` defines two services in one project, in the London region (next to the Supabase database; match yours):
   - **api**: the FastAPI app, served at `/api/*`
   - **web**: the Vite app, serving every other path

   The browser calls `/api` on the same domain, so no service bindings are needed.
2. Add these under **Settings → Environment Variables** (for Production):

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the transaction pooler URL from above (`postgresql+psycopg://…:6543/postgres`) |
   | `SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `SUPABASE_JWT_SECRET` | the legacy JWT secret if your project shows one; otherwise leave it out (signing keys are fetched automatically) |
   | `OWNER_EMAIL` | your login email |
   | `SYNC_TOKEN` | a long random string: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `VITE_SUPABASE_URL` | same as `SUPABASE_URL` |
   | `VITE_SUPABASE_ANON_KEY` | the **anon / publishable** key (safe for the browser) |

   The service-role key does **not** go into Vercel.
3. Deploy. Open `https://<your-app>.vercel.app` on your phone and sign in. To make it feel like an app, use Safari's **Share → Add to Home Screen**.

## 3. Mac sync (Zwift + HealthFit)

`sync/fit_sync.py` uploads any `.fit` file it hasn't uploaded before. It runs whenever the Zwift or HealthFit folder changes, and once an hour as a fallback. It only uses macOS's built-in Python.

1. Create `~/.config/lockedin/sync.env`:
   ```
   LOCKEDIN_API=https://<your-app>.vercel.app
   SYNC_TOKEN=<same value as in Vercel>
   ZWIFT_ACTIVITIES_DIR=~/Documents/Zwift/Activities
   HEALTHFIT_DIR=~/Library/Mobile Documents/iCloud~com~altifondo~HealthFit/Documents
   ```
   Check `HEALTHFIT_DIR` once HealthFit has exported something (see section 4). Leave the line out until then.
2. Install the background agent:
   ```bash
   sync/install.sh
   ```
3. **Give Python access to your folders.** macOS blocks background apps from reading `~/Documents` and iCloud Drive. `install.sh` prints the exact Python file to allow; it's the real interpreter behind `/usr/bin/python3`, usually under `/Library/Developer/CommandLineTools/`. Open **System Settings → Privacy & Security → Full Disk Access**, click **+**, press **⌘⇧G**, paste that path and add it.
4. Check the log:
   ```bash
   tail -f ~/Library/Logs/lockedin-sync.log
   ```
   A healthy run looks like `uploaded 1, already there 42, still being written 0, errors 0`. A line saying it *can't read* a folder means step 3 isn't done yet.

Uninstall with `sync/uninstall.sh`. A file the server can't read is listed in the log and skipped, and newer files still upload. Files that are still being written (like Zwift's ride in progress) are skipped and picked up a few minutes later. Files over 4 MB are skipped with a warning; upload those on the **Import** page.

## 4. Apple Watch workouts via HealthFit (iPhone)

HealthFit is a third-party app (about €8, one-time). It turns your Apple Health workouts into `.fit` files.

> The menu names below come from HealthFit's documentation, not a hands-on test yet. **Check them when you install it.**

1. Install **HealthFit** from the App Store and allow it to read Health data (workouts, heart rate, distance, swimming strokes).
2. Turn on automatic export: **Settings → Auto Sync / Auto Export**, choose **iCloud Drive**, file format **FIT**.
3. On your Mac, find the folder in Finder: **iCloud Drive → HealthFit**. Put its path in `HEALTHFIT_DIR` (section 3), then run `sync/install.sh` again so it watches that folder too.
4. To bring in older workouts, select them in HealthFit's workout list and export them to the same iCloud folder. The sync uploads them, and duplicates are skipped.

If your Watch also recorded a Zwift ride (as "Indoor Cycle"), only the Zwift ride counts. If the Zwift file has no heart rate, the Watch's heart rate is copied onto it. A Watch strength workout during a Hevy session is merged the same way. Walks are kept but don't count toward your training totals.

## 5. Hevy (gym)

In Hevy: **Profile → Settings → Export & Import Data → Export Workouts**. Save the CSV and upload it on the **Import** page. Always upload the **full** export. Workouts you already have are left alone, edited ones are updated, and renamed ones are updated in place.

## 6. Dashboard & focus suggestions

The **Overview** page answers two questions: am I improving, and what should I focus on next. Everything there is calculated from your data. There's no AI involved yet; the coach comes in plan 3.

- **Focus this week** shows up to 3 suggestions.
  - **Gym:** each muscle gets weekly working sets: a set counts 1 for the main muscle and ½ for helping muscles, and warm-ups don't count. A muscle below its minimum is "low", and you get an exercise to add:
    - **One you already do:** the weight comes from your recent sets (3 × 8–12, about 2 reps in reserve).
    - **A new one:** estimated from a related lift you do, then lowered by 20% and marked "estimate, start light". With no basis for an estimate, no weight is shown.
    - **Dumbbell weights** use the same convention as your Hevy logs. Set it under **Body → Dumbbell weights in Hevy** (default: total of both dumbbells).
  - **Bike/run:** each session is labelled easy, steady, hard or long from time in heart-rate or power zones. If your last 3 weeks are missing a long session or a hard one, or are mostly hard, you get a concrete session with your own zone numbers.
- **Recent wins** are personal bests from the last 2 weeks (estimated 1RM, 20-min power, longest, fastest) and "more consistent than last year".
- **Streak** counts consecutive weeks with at least 2 sessions. After 7 days without training, the page opens with a "Welcome back" card instead of comparisons.
- **Trends** has a page per sport: power, efficiency and best 20 min for the bike; pace and aerobic efficiency for runs; pace per 100 m for swims; and for the gym, muscle coverage, volume and progress per exercise. Exercises the library doesn't know appear under **Tag your exercises**.

**Better numbers:**
- Enter your **FTP** on the Body page. Zwift shows it in your profile. Estimating it from regular rides underestimates it, which makes rides look harder than they were.
- Set **max heart rate** if you know it. Otherwise it's taken from your highest recorded value, or estimated as 220 − age.

**Deploying an update with a new migration:** run `supabase db push` **before** `git push`, so the database is ready when the new code goes live.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "File too large (max 4 MB)" | Vercel limits request size. FIT files are normally far smaller; check that you picked the right file. |
| The sync log says it can't read a folder | Give Full Disk Access to the Python file named in that log line (section 3). |
| Sync log shows `server said 401` | `SYNC_TOKEN` in `sync.env` doesn't match Vercel's, or is shorter than 16 characters. |
| You're logged out right after signing in | `OWNER_EMAIL` on the server doesn't match the account you signed in with. |
| Everything is slow or failing after a quiet week | Supabase paused the project; restore it in the dashboard. |

## Layout

```
lockedin/         FastAPI app (imports, dedupe, routes)
supabase/         config + SQL migrations
sync/             Mac uploader + launchd agent
web/              React + Vite app
samples/          synthetic FIT files and Hevy CSVs for testing
tests/            pytest suite
```
