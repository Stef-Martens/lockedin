# LockedIn

A personal training tracker for one person. It collects:

- **Zwift rides** from the Mac where Zwift runs
- **Apple Watch runs, swims and other workouts** through the iPhone app HealthFit
- **Hevy gym workouts** from Hevy's CSV export

It also stores **body measurements** like weight, chest and arms. Everything is in one place you can open on your phone.

It runs on **Vercel** (the web app plus a Python API) and **Supabase** (Postgres plus login). A small script on your Mac uploads new ride and workout files automatically.

On top of that it has an overview with focus tips, a workout planner, an agenda that sends rides to Zwift, training load, and an AI coach. The design notes and plans are in `docs/superpowers/`.

---

## 1. Run it locally

You need Docker Desktop (running), the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started), Python 3.12+ and Node 20+.

```bash
make install                      # Python venv + web dependencies
cp .env.example .env              # then fill in the three keys below
supabase start                    # first run downloads the Docker images (a few minutes)
supabase status                   # copy "anon key" → VITE_SUPABASE_ANON_KEY, "service_role key" → SUPABASE_SERVICE_ROLE_KEY,
                                  # "JWT secret" → SUPABASE_JWT_SECRET (local only; it's a public default)
supabase db reset                 # creates the tables
make owner EMAIL=you@example.com  # the only account; asks for a password; must match OWNER_EMAIL in .env
make dev                          # API on :8000, web app on http://127.0.0.1:5173
```

Run the tests with `make test`. It creates a separate `lockedin_test` database, so your local data is safe. `make lint` runs ruff and ESLint. GitHub Actions runs both, plus the web tests and build, on every push.

**Dependencies:** `pyproject.toml` is the one list. Vercel installs the exact versions in `uv.lock`, and `requirements.txt` mirrors it. After changing a dependency, run `make lock` and commit both files. `make lock UPGRADE=--upgrade` moves everything to the newest allowed version.

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
     OWNER_EMAIL=you@example.com .venv/bin/python scripts/create_owner.py --email you@example.com
   ```
   It asks for the password, so it doesn't end up in your shell history.
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
   | `SUPABASE_JWT_SECRET` | the legacy JWT secret if your project shows one; otherwise leave it out (signing keys are fetched automatically). Never the local stack's default: outside localhost that, or any secret under 32 characters, is refused |
   | `OWNER_EMAIL` | your login email |
   | `OWNER_ID` | optional: your Supabase user id (**Authentication → Users**). When set, a login must match it as well as the email |
   | `SYNC_TOKEN` | a long random string: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `VITE_SUPABASE_URL` | same as `SUPABASE_URL` |
   | `VITE_SUPABASE_ANON_KEY` | the **anon / publishable** key (safe for the browser) |
   | `ANTHROPIC_API_KEY` | for the AI coach (section 10); from [console.anthropic.com](https://console.anthropic.com) → API keys. Optional: without it, the Coach page shows a setup message |
   | `COACH_DAILY_BUDGET_USD` | optional: the most the coach may spend per day (default 5) |

   The service-role key does **not** go into Vercel.
3. Deploy. Open `https://<your-app>.vercel.app` on your phone and sign in. To make it feel like an app, use Safari's **Share → Add to Home Screen**.

## 3. Mac sync (Zwift + HealthFit)

`sync/fit_sync.py` uploads any `.fit` file it hasn't uploaded before. It runs whenever the Zwift or HealthFit folder changes, and every 15 minutes as a fallback. It only uses macOS's built-in Python.

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

Uninstall with `sync/uninstall.sh`. A file the server can't read is listed in the log once and tried again a day later, and newer files still upload. Files that are still being written (like Zwift's ride in progress) are skipped and picked up a few minutes later. Files over 4 MB are skipped with a warning; upload those on the **Import** page.

The sync remembers what it already uploaded in `~/Library/Application Support/lockedin/fit-sync-state.json`, so it doesn't re-read every file or pull old HealthFit files back from iCloud. **If you ever reset the server's database, delete that file** so everything is uploaded again.

## 4. Apple Watch workouts via HealthFit (iPhone)

HealthFit is a third-party app (about €8, one-time). It turns your Apple Health workouts into `.fit` files.

> The menu names below come from HealthFit's documentation, not a hands-on test yet. **Check them when you install it.**

1. Install **HealthFit** from the App Store and allow it to read Health data (workouts, heart rate, distance, swimming strokes).
2. Turn on automatic export: **Settings → Auto Sync / Auto Export**, choose **iCloud Drive**, file format **FIT**.
3. On your Mac, find the folder in Finder: **iCloud Drive → HealthFit**. Put its path in `HEALTHFIT_DIR` (section 3), then run `sync/install.sh` again so it watches that folder too.
4. To bring in older workouts, select them in HealthFit's workout list and export them to the same iCloud folder. The sync uploads them, and duplicates are skipped.

If your Watch also recorded a Zwift ride (as "Indoor Cycle"), only the Zwift ride counts; the same goes for a Zwift run and the Watch's indoor run. If the Zwift file has no heart rate, the heart rate of the Watch file covering most of the ride is copied onto it. A Watch strength workout during a Hevy session is merged the same way, and shows up again if you later move that Hevy workout. Walks are kept but don't count toward your training totals.

A multisport workout (e.g. bike → run) comes in as one session per leg. Pool swim pace counts only your lengths, not the rest at the wall.

## 5. Hevy (gym)

In Hevy: **Profile → Settings → Export & Import Data → Export Workouts**. Save the CSV and upload it on the **Import** page. Always upload the **full** export. Workouts you already have are left alone, edited ones are updated, and renamed ones or ones whose start time you changed are updated in place. An exercise you do twice in one workout (e.g. bench, flyes, bench again) stays two separate blocks.

**Estimated 1RM** (Epley) is worked out from sets of up to 20 reps and used to pick working weights. Personal bests and goal progress only count sets of 12 reps or fewer, where the estimate is reliable. Assisted lifts (assisted pull-ups, dips) never get one, since more assistance doesn't mean stronger.

## 6. Dashboard & focus suggestions

The **Overview** page answers two questions: am I improving, and what should I focus on next. Everything there is calculated from your data, not by AI. The AI coach (section 10) builds on the same numbers.

- **Focus this week** shows up to 3 suggestions.
  - **Gym:** each muscle gets weekly working sets: a set counts 1 for the main muscle and ½ for helping muscles, and warm-ups don't count. A muscle below its minimum is "low", and you get an exercise to add:
    - **One you already do:** the weight comes from your recent sets (3 × 8–12, about 2 reps in reserve).
    - **A new one:** estimated from a related lift you do, then lowered by 20% and marked "estimate, start light". With no basis for an estimate, no weight is shown.
    - **Dumbbell weights** use the same convention as your Hevy logs. Set it under **Body → Dumbbell weights in Hevy** (default: total of both dumbbells).
  - **Gym weeks:** while you've trained for less than 4 weeks, sets are averaged over the weeks you have, so a new start doesn't show every muscle as low.
  - **Bike/run:** each session is labelled easy, steady, hard or long from time in heart-rate or power zones. If your last 3 weeks are missing a long session or a hard one, or are mostly hard, you get a concrete session with your own zone numbers. Easy and long runs are prescribed at 65–78% of max heart rate.
- **Zones:**
  - Heart rate: zones start at 72, 82, 87 and 92% of max (Seiler's 5-zone scale). "Hard" means zone 4 and up, so 87% or more.
  - Power: Coggan zones from your FTP, with zone 5 open-ended. Rides are zoned on 30-second average power, so short surges on Zwift hills don't count as hard.
- **Recent wins** are personal bests from the last 2 weeks (estimated 1RM, 20-min power, longest, fastest) and "more consistent than last year".
  - **Fastest run or swim** only beats earlier ones of a similar distance (within 10%).
  - **More consistent** compares sessions per week over the last 8 weeks with the same 8 weeks last year.
- **Streak** counts consecutive weeks with at least 2 sessions. After 7 days without training, the page opens with a "Welcome back" card instead of comparisons.
- **Trends** has a page per sport: power, efficiency and best 20 min for the bike; pace and aerobic efficiency for runs; pace per 100 m for swims; and for the gym, muscle coverage, volume and progress per exercise. Exercises the library doesn't know appear under **Tag your exercises**.

**Muscles:**
- The **Muscles** page shows your week on a body, front and back. Every muscle starts grey on Monday and fills in as you log gym sets: darker green for a little, green when it's in its weekly target range, bright lime for lots.
- **Rides, runs and swims** draw stripes instead (blue, orange, teal). Bike and run stripe the legs; swims stripe the lats, shoulders and triceps. They never count as gym sets, so a week of Zwift still shows your legs as "no gym work yet" and the focus tips keep suggesting leg work.
- **Hover a muscle** to see:
  - this week's sets against its target, with the days and exercises
  - your cardio minutes, for muscles a sport uses
  - the last 6 weeks
  - how its main lift has moved (estimated 1RM, first vs. latest session in the last 8 weeks)
- **Untrained muscles:** they show when you last trained them; in the current week they also show the focus engine's suggestion.
- **Click** a muscle to keep its details in the side column; Esc lets go.
- **Earlier weeks:** the ‹ › arrows step back through them, and the URL remembers the week.
- **Show as list** gives the same numbers as a table.

**Body check-ins and reminders:**
- **Body** is one check-in form: one date, every measurement on one screen (weight, chest, shoulders, arms, waist, hips, thighs). Fill in what you measured; blank fields are skipped. Saving the same date again replaces those values. Each field says where to put the tape, and History shows the change since your previous check-in.
- **Reminder:** pick every 1, 2 or 4 weeks, and choose whether to include the Hevy upload. **Add to calendar** downloads a repeating event; open it to add it to iPhone or Mac Calendar. It starts on your next due date at 09:00 and links to the Body page.
- The **Overview** shows "Body check-in due" when it's time, and when you last uploaded your Hevy export. Hevy counts as due after 7 days.

**Better numbers:**
- Enter your **FTP** on the Body page. Zwift shows it in your profile. Estimating it from regular rides underestimates it, which makes rides look harder than they were.
  - **It's kept per date:** a new FTP applies from today on, and rides before it keep the FTP that was true then. Before your first entry, 95% of your best 20 minutes is used.
  - **Zwift intervals** are only marked on target, above or below against an FTP you entered for that day. With only the estimate, they show without a verdict.
- Set **max heart rate** if you know it. Otherwise it's your best 30-second heart rate of the last year, so one sensor spike doesn't skew every zone. Without heart-rate streams it's your second-highest session maximum, and without any data it's estimated as 208 − 0.7 × age.

**Training load** (top of Trends): every session gets a load score.
- **Rides with power:** TSS from your FTP.
- **Runs, swims and rides without power:** heart-rate TSS (an hour at threshold heart rate, about 89% of max, scores 100).
- **Gym:** a flat 40 per hour, as a rough estimate.
- **Fitness** is your 42-day average load and **fatigue** your 7-day average. **Form** is fitness minus fatigue: well below zero means you're carrying fatigue, around zero is steady training, above zero means fresh.

**Deploying an update with a new migration:** run `supabase db push` **before** `git push`, so the database is ready when the new code goes live.

## 7. Workout planner

Before the gym, tap **Plan a workout**, on the Overview or the Muscles page.

- **Your days are your Hevy routines.** When you start a workout from a routine in Hevy, the workout gets the routine's name. Every name you've used in the last 60 days becomes a day you can pick, e.g. "Chest - Schouders - Triceps". Its exercises are the ones from the last time you did it.
- **A plan is that routine with today's changes marked:**
  - **Targets:** each exercise shows what you did last time. If every set at your top weight reached 12 reps, it says go up by about 5% of the weight, rounded to the equipment's step (2.5 kg barbell or cable, 5 kg machine, 2 kg per dumbbell), and never more than 10% unless one step already is. Otherwise: same weight, aim for one more rep.
  - **Lifts you haven't done in a while** start lighter: 10% after 3 weeks, 20% after 8 weeks, with no "go up" until you're back in the groove.
  - **Variety:** at most one stuck lift (no progress in 6 weeks) is swapped for another exercise for the same muscle. A lift one of your goals is about is never swapped.
  - **Extras, if you have time:** at most two exercises for muscles this day trains but your routine misses, with weights from your own lifts. New exercises are marked "start light".
  - **Just what I've missed** is an alternative day: up to 5 exercises for your least-trained muscles.
  - **After a week or more off,** plans keep your recent weights and skip the extras; lifts away for 3 weeks or more still start lighter.
- **Per exercise:**
  - **Swap** gives another exercise for the same muscle.
  - **⋯ → Skip for today** greys an exercise out.
  - **⋯ → Don't suggest this again** is only shown on suggested exercises.
- **Plans are saved for the day,** so they're the same when you reopen them at the gym. They rebuild by themselves the next day, after a newer Hevy import for that routine, or when you change preferences.
- **Preferences** (from the planner):
  - **Muscles to leave out**, e.g. lower back. The planner never targets them, they don't show as "no gym work yet" on the Muscles page, and the focus tips skip them. Exercises that only load them along the way (squats, rows) can still appear.
  - **Exercises never to suggest.**
  - **Notes for the coach.**

  The AI coach reads all of these.
- **Goals:** goals you set with the coach show on the Overview. A goal about one lift (e.g. "Bench 100 kg") also shows next to that exercise in your plans.

To deploy: `supabase db push`, then `git push`.

## 8. Today, session pages and goals

- **Today** sits at the top of the Overview: today's agenda as a to-do list.
  - Each done session gets a tick and what you did ("Done · 65′ · 156 W · intervals on target"), with **See how it went**.
  - Open gym days have **Plan it**.
  - Underneath is the next planned day.
- **Session pages:** click any session in the agenda to open its own page.
  - **Before:** the full plan.
    - **Zwift:** every part with times and watts, sweet-spot minutes, estimated TSS, and the FTP used.
    - **Runs and swims:** distance or time, pace range, heart-rate zone.
    - **Gym:** the planner's targets.
  - **After:** the plan next to what you did.
    - **Zwift:** your power over the planned target, and each interval's watts marked on target (within 3%), above or below.
    - **Runs:** totals, a pace chart with the target band, splits per km, and time in heart-rate zones.
    - **Swims:** distance, time, pace per 100 m, lengths and strokes.
    - **Gym:** each planned exercise against the sets you logged: done, close, skipped, skipped by you, or added.
  - Edit, move or delete the session from the same page.
- **Goals steer the whole app.** Each goal has a kind (gym, bike, run, swim, body or general), and a lift goal knows its lift.
  - **Progress:** goals show on the Overview with a bar where it can be measured:
    - lift goals by your best estimated 1RM; a goal with reps ("80 kg for 5 reps") by your heaviest set of at least that many reps
    - FTP goals by your FTP
    - run and swim distance goals by your longest run or swim in the last 8 weeks
    - run and swim time goals ("5k under 25 min") by your best time over that distance, from sessions of about that length. "Marathon" and "half marathon" count as distances.
    - body goals from your measurement when you set the goal

    Relative goals like "lose 5 kg", pace goals, timed bike goals, and anything that can't be measured honestly show as text only.
  - **Focus tips:**
    - Muscles your goal lift uses come first ("helps: Bench 100 kg").
    - A run, ride or swim goal always brings a session of that sport ("toward: Run a 10K").
  - **Planner:** your goal lift gets one extra heavy set, up to 4, and never during a comeback. Extras for its muscles come first.
  - **Muscles page:** muscles your goal lift trains say so.
  - **The coach** links agenda sessions to the goal they serve, and gives runs and swims targets.

## 9. Agenda

The **Agenda** tab shows your week, Monday to Sunday, with what to do each day.

- **Planning with the coach:** work out a week with the coach, then say something like "put it in my agenda". It only writes after you agree.
  - **Changing it by chat:** "move the sweet spot to Friday" works too.
  - **What the coach sees:** today's and tomorrow's plan, in every chat.
- **Your own changes:**
  - Tap a session to change its title, day or note, mark it optional, or delete it.
  - Use **+ Add** on a day to add a gym routine, a run, a swim, a rest day or a note.
- **Zwift workouts land in Zwift by themselves.** Rides the coach plans come with power targets.
  - **How:** your Mac sync writes them into Zwift's custom workouts folder (`Documents/Zwift/Workouts/<your Zwift ID>`) as `YYYY-MM-DD Title.zwo`.
  - **Finding them:** restart Zwift and they're under **Custom Workouts**, sorted by date.
  - **When you move or delete one,** the file follows at the next sync. Past days are cleaned up.
  - **Your own files are safe:** the sync keeps a list (`.lockedin-workouts.json`) and only ever changes files it wrote itself.
  - **The tag:** a session shows **In Zwift ✓** once your Mac has fetched it.
- **Ticking off happens by itself:**
  - A Zwift session ticks off when a ride comes in that day.
  - A gym day ticks off when a Hevy workout with that routine's name comes in.
  - Runs and swims tick off by a run or swim that day.
  - Anything left unticked just stays that way. There's no red.
- **Today** shows at the top of the Overview.
- **The sync now runs every 15 minutes,** so plans reach Zwift quickly. Run `sync/install.sh` once more to switch your Mac over.

To deploy: `supabase db push`, then `git push`, then re-run `sync/install.sh` on your Mac.

## 10. AI coach

The **Coach** page is a chat with Claude about your training. Ask things like "what should I focus on this week?", "plan my next gym session" or "am I getting fitter on the bike?". It looks at your data before answering, so the advice uses your own lifts, zones and sessions.

- **What it can see:** your activities, gym sets, exercises, body measurements, profile and goals. It starts from the same focus analysis as the Overview, and it can run its own queries for anything else.
- **What it can't do:**
  - It can't see your raw uploaded files, the import log, its own chat history or the login accounts table.
  - It can't change any of your data. Its queries run under a separate read-only database role, inside a read-only transaction, with a 3-second time limit and at most 200 rows per query.
  - The only thing it can write is a goal, and only after you agree in the chat.
- **Goals:** tell it what you want to work on and it proposes a goal. Say yes and it's saved; active goals show next to the chat. About every 4 weeks it asks whether your goals still fit.
- **Chats are saved**, so you can come back to one and continue.
- **Setup:** add `ANTHROPIC_API_KEY` in Vercel (section 2) and redeploy. The key stays on the server; the browser never sees it.
- **Model:** `claude-opus-5-5` by default. To change it, set `ANTHROPIC_MODEL` to a model that supports mid-conversation system messages and `fallbacks: "default"`: Opus 5.5, Opus 5 or Fable 5.1. Others reject every message.
- **If Claude declines a request:** Anthropic automatically retries it on another Claude model. This is the API's "fallbacks" option, and it's always on.
- **Cost:** pay-as-you-go on your Anthropic account, at $4 per million tokens in and $20 per million out. A typical question costs roughly 5–15 cents; long chats cost more, because the whole chat is sent each time. Start a new chat when you change topic, and set a monthly spend limit in the Anthropic console.
  - **Daily cap:** every call's tokens are logged, and once today's estimated spend reaches `COACH_DAILY_BUDGET_USD` (default $5) the coach says so instead of answering, until tomorrow.
  - **Time limit:** a long answer stops looking things up after 4 minutes and answers with what it has, so it finishes within Vercel's 5-minute limit.

To deploy the coach: `supabase db push`, add `ANTHROPIC_API_KEY` in Vercel, then `git push`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "File too large (max 4 MB)" | Vercel limits request size. FIT files are normally far smaller; check that you picked the right file. |
| The sync log says it can't read a folder | Give Full Disk Access to the Python file named in that log line (section 3). |
| Sync log shows `server said 401` | `SYNC_TOKEN` in `sync.env` doesn't match Vercel's, or is shorter than 16 characters. |
| You're logged out right after signing in | `OWNER_EMAIL` (or `OWNER_ID`, if set) on the server doesn't match the account you signed in with, or `SUPABASE_JWT_SECRET` is the local default or too short (the API logs a warning). |
| A file the sync says the server can't read stays unread after a fix | The server remembers unreadable files. Run `update fit_files set unreadable = false` in the Supabase SQL editor, then wait for the next daily retry or upload it on **Import**. |
| Everything is slow or failing after a quiet week | Supabase paused the project; restore it in the dashboard. |
| Coach says "The Anthropic API key was rejected" | Check `ANTHROPIC_API_KEY` in Vercel, then redeploy (env changes only apply to new deployments). |
| Coach says "Claude is busy right now" | Rate limit or a temporary outage. Wait a minute and press Retry. |
| Coach says today's budget is used up | Raise `COACH_DAILY_BUDGET_USD` in Vercel and redeploy, or wait until tomorrow. |

## Layout

```
lockedin/         FastAPI app (imports, dedupe, routes)
supabase/         config + SQL migrations
sync/             Mac uploader + launchd agent
web/              React + Vite app
samples/          synthetic FIT files and Hevy CSVs for testing (`make samples` rebuilds them)
tests/            pytest suite
.github/          CI: lint, API tests on Postgres 17, web tests and build
```
