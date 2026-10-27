"""The Forecast page: goals, fitness ahead, race times and FTP, each projected from the owner's own data."""

import calendar
from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.fitness import _day_start, ftp_at, known_ftp, known_ftp_at
from lockedin.forecast.ahead import fitness_ahead
from lockedin.forecast.goals import WEEKS_BACK, goal_forecasts
from lockedin.forecast.race import race_forecast
from lockedin.forecast.trend import fit, month_part, project
from lockedin.timeoff import entries
from lockedin.timeutil import TZ

FTP_AHEAD_WEEKS = 12
WHO = {"zwift": "Zwift's FTP", "owner": "Your FTP"}


def ftp_forecast(conn: Connection, now: datetime) -> dict | None:
    """FTP over time as Zwift (or the owner) gave it, and where it's heading when there's enough of a trend."""
    today = now.astimezone(TZ).date()
    days = conn.execute(text(
        "select distinct effective_from from ftp_history where ftp is not null and effective_from <= :d order by 1"
    ), {"d": today}).scalars().all()
    history: list[list] = []
    for d in days:
        w = known_ftp_at(conn, _day_start(d))
        if w and (not history or history[-1][1] != round(w)):
            history.append([d.isoformat(), round(w)])
    k = known_ftp(conn, now)
    if k is None:
        est = ftp_at(conn, now)
        if not est:
            return None
        return {"now": round(est), "source": "estimate", "history": [], "projection": [],
                "summary": f"About {round(est)} W, estimated from your best 20 minutes until Zwift's FTP is known."}
    summary = f"{WHO[k.source]}: {k.w} W"
    if k.since:
        summary += f" since {k.since.day} {calendar.month_abbr[k.since.month]}"
    if len(history) > 1 and history[-2][1] != k.w:
        summary += f", {'up' if k.w > history[-2][1] else 'down'} from {history[-2][1]}"
    summary += "."
    projection: list[list] = []
    trend = fit([(datetime.fromisoformat(d).date(), float(w)) for d, w in history], today)
    if trend and trend.per_week > 0:
        proj = project(trend, FTP_AHEAD_WEEKS, flatten=True)
        projection = [[d.isoformat(), round(m, 1), round(lo, 1), round(hi, 1)] for d, m, lo, hi in proj]
        summary += f" Heading for about {round(proj[-1][1])} W by {month_part(proj[-1][0], today)}."
    return {"now": k.w, "source": k.source, "history": history, "projection": projection, "summary": summary}


def time_off(conn: Connection, now: datetime) -> list[dict]:
    """Time off since the charts' first week, for shading."""
    since = now.astimezone(TZ).date() - timedelta(weeks=WEEKS_BACK)
    return [{"start": e["start"].isoformat(), "end": e["end"].isoformat(), "reason": e["reason"], "label": e["label"]}
            for e in entries(conn, since)]


def forecast(conn: Connection, now: datetime) -> dict:
    return {"goals": goal_forecasts(conn, now), "race": race_forecast(conn, now),
            "fitness": fitness_ahead(conn, now), "ftp": ftp_forecast(conn, now), "time_off": time_off(conn, now)}
