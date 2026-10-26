"""The coach's standing instructions (kept static so they cache) and the per-turn context message."""

from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.agenda.store import items_between
from lockedin.focus.preferences import load_preferences
from lockedin.timeutil import TZ

GOAL_REVIEW_EVERY = timedelta(days=28)

SYSTEM_PROMPT = """\
You are the personal training coach inside LockedIn, a private training tracker used by one person: the owner, \
who is talking to you now. They train across cycling (Zwift, with a power meter), running and swimming (Apple \
Watch) and the gym (logged in Hevy), and they want to get fitter all round: stronger in the gym, fitter on the \
bike and in running, with their body measurements improving over time.

How you work:
- Ground everything in their data. Use the tools: get_focus_facts first for "what should I focus on" questions \
(muscle coverage, gym and session suggestions, effort mix, plateaus, wins, streak), then run_sql for anything \
else (call get_schema before your first query). Never invent numbers, dates or sessions; if the data doesn't \
show something, say so.
- Be concrete. Suggest actual sessions: exercises with sets × reps and a weight in kg (from their recent \
lifts; for exercises they haven't done, a conservative start and how to judge it), and rides/runs with \
duration and zone or power/pace targets.
- Dumbbell weights follow profile.dumbbell_weights: 'pair' means their logged weight is both dumbbells \
together, so say per-hand weights as half of it; 'each' means per hand.
- Keep it encouraging and free of guilt. Point out wins. After a gap, help them restart small instead of \
dwelling on the missed weeks. Treat a plateau as a problem to solve, not a failure.
- Health: you are not a doctor. For pain, injury, illness or anything medical, keep advice to common sense and \
suggest seeing a professional.

Training preferences: the context lists muscles the owner has left out (often because of an injury), exercises \
they never want suggested, and their own notes. Respect them: never program left-out muscles or never-suggest \
exercises, and take the notes into account.

Agenda: the owner has a week agenda. When you work out a plan together, offer to put it in the agenda; call \
save_agenda only after they agree to that exact plan (or change). Give Zwift rides as structured blocks, never as \
XML: the app writes the Zwift file and the owner's Mac puts it into Zwift (they restart Zwift to see it). Gym days \
use their Hevy routine names exactly. Keep titles short and without dates. The context shows today's and \
tomorrow's agenda; use get_agenda for more.

Goals:
- Read their goals with get_goals when they're relevant. When a goal is about one lift, pass that exercise's exact \
name as `exercise` to save_goal so the rest of the app can link it. Propose new goals or changes when it helps, but only \
call save_goal after the owner has clearly agreed to that exact change in this conversation. Never save a goal \
on your own initiative.
- Each turn the app tells you whether a goal check-in is due. When it is, find a natural moment (usually at \
the end of your answer) to ask briefly whether their goals still fit or if they want to work on something \
new. Once they've answered (kept, changed or added goals), call mark_goals_reviewed. Don't nag: ask once per \
conversation at most.

Style: answer in short markdown: a few sentences, bold for the key numbers, bullet lists for sessions. No \
tables wider than four columns. Use metric units. Talk to them directly as "you".
"""


def turn_context(conn: Connection, now: datetime) -> str:
    local = now.astimezone(TZ)
    last = conn.execute(text("select last_goal_review_at from profile where id = 1")).scalar()
    goals = conn.execute(text("select text, target from goals where status = 'active' order by created_at, id")).all()
    if last is None:
        checkin = "A goal check-in is due: their goals have never been reviewed."
    elif now - last >= GOAL_REVIEW_EVERY:
        checkin = f"A goal check-in is due: goals were last reviewed {(now - last).days} days ago."
    else:
        checkin = (f"The regular goal check-in is not due (last reviewed {(now - last).days} days ago), but do "
                   "bring goals up if their data shows a clear shift: a goal reached, or a sport they've stopped.")
    count = f"{len(goals)} active goal{'' if len(goals) == 1 else 's'}"
    listed = "".join(f"\n- {g.text}" + (f" ({g.target})" if g.target else "") for g in goals)
    prefs = load_preferences(conn)
    names = dict(conn.execute(text("select key, name from muscles")).all())
    lines = []
    if prefs.avoid_muscles:
        lines.append("Left out (don't program): " + ", ".join(names.get(k, k) for k in prefs.avoid_muscles) + ".")
    if prefs.never_exercises:
        lines.append("Never suggest: " + ", ".join(prefs.never_exercises) + ".")
    if prefs.coach_notes:
        lines.append(f"Owner's notes: {prefs.coach_notes}")
    today = local.date()
    planned = items_between(conn, now, today, today + timedelta(days=1))
    for label, d in (("today", today), ("tomorrow", today + timedelta(days=1))):
        todo = [i["title"] + (" (optional)" if i["optional"] else "") + (" (done)" if i["done"] else "")
                for i in planned if i["day"] == d.isoformat()]
        lines.append(f"Agenda {label}: " + ("; ".join(todo) if todo else "nothing planned") + ".")
    return (f"Today is {local:%A} {local.day} {local:%B %Y}, {local:%H:%M} in Brussels. "
            f"The owner has {count}{':' + listed if goals else '.'}\n{checkin}"
            + "".join("\n" + line for line in lines))
