"""Zwift's FTP, read back from the app's own workouts: in ERG mode Zwift holds each step at its share of
Zwift's FTP, so watts ÷ planned share gives that FTP. Zwift's ride files don't say it outright."""

from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import Connection, text

from lockedin.agenda.parts import parts
from lockedin.agenda.store import items_between
from lockedin.agenda.zwo import ZwiftWorkout
from lockedin.fitness import record_zwift_ftp
from lockedin.timeutil import TZ

SETTLE_S = 20  # ERG takes a few seconds to reach a new target: skip the start of each step
CHUNK_S = 60  # steady steps are judged minute by minute
MIN_SHARE = 0.4  # below this, Zwift workouts are free-spin territory
ERG_AGREE = 0.03  # in ERG every minute of every step gives the same FTP to within a few percent
MIN_AGREEING = 5  # minutes: one 20-minute steady block is plenty, a stray minute isn't
AGREEING_SHARE = 0.75  # a faded interval or a surge must not hide an otherwise ERG ride
SANE_FTP = (50, 600)
CATCH_UP = timedelta(days=14)


def _minutes(blocks: dict, t: list[int], power: list) -> list[tuple[float, float]]:
    """(total watts, total planned share) for each whole minute of a steady step the ride covered."""
    at = {x: i for i, x in enumerate(t)}
    out = []
    for p in parts(ZwiftWorkout(**blocks), None):
        if p["from_frac"] != p["to_frac"] or p["from_frac"] < MIN_SHARE:
            continue
        for start in range(p["start_s"] + SETTLE_S, p["end_s"] - CHUNK_S + 1, CHUNK_S):
            watts = [power[at[x]] for x in range(start, start + CHUNK_S) if x in at and power[at[x]]]
            if len(watts) >= 0.8 * CHUNK_S:
                out.append((sum(watts), p["from_frac"] * len(watts)))
    return out


def learn_from_ride(conn: Connection, activity_id: int) -> int | None:
    """Zwift's FTP from a Zwift ride of one of the app's workouts, recorded for the ride's day; None when the
    ride wasn't one, or wasn't ridden in ERG (the steps disagree)."""
    a = conn.execute(text(
        "select a.start_at, s.t_offset, s.power from activities a join activity_streams s on s.activity_id = a.id "
        "where a.id = :i and a.source = 'zwift' and a.sport = 'bike' and a.superseded_by is null"
    ), {"i": activity_id}).first()
    if a is None or not a.power:
        return None
    day = a.start_at.astimezone(TZ).date()
    item = next((i for i in items_between(conn, a.start_at, day, day)
                 if i["activity_id"] == activity_id and i["zwift"]), None)
    if item is None:
        return None
    minutes = _minutes({"blocks": item["zwift"]["blocks"]}, list(a.t_offset), list(a.power))
    if not minutes:
        return None
    mid = median(w / share for w, share in minutes)
    agreeing = [(w, share) for w, share in minutes if abs(w / share - mid) <= ERG_AGREE * mid]
    if len(agreeing) < MIN_AGREEING or len(agreeing) < AGREEING_SHARE * len(minutes):
        return None
    # All agreeing work over all planned work: Zwift's whole-watt targets round each step a little.
    ftp = round(sum(w for w, _ in agreeing) / sum(share for _, share in agreeing))
    if not SANE_FTP[0] <= ftp <= SANE_FTP[1]:
        return None
    record_zwift_ftp(conn, day, ftp, activity_id)
    return ftp


def learn_recent(conn: Connection, now: datetime) -> None:
    """Try the last two weeks' Zwift rides that haven't taught anything yet and fell on a day with one of the
    app's Zwift workouts: rides imported before their workout was planned, or before this existed."""
    ids = conn.execute(text(
        "select a.id from activities a where a.source = 'zwift' and a.sport = 'bike' and a.superseded_by is null "
        "and a.start_at > :since and a.start_at <= :now "
        "and not exists (select 1 from ftp_history h where h.activity_id = a.id) "
        "and exists (select 1 from agenda_items i where i.zwift is not null "
        "and i.day = (a.start_at at time zone 'Europe/Brussels')::date) order by a.start_at"
    ), {"since": now - CATCH_UP, "now": now}).scalars().all()
    for activity_id in ids:
        learn_from_ride(conn, activity_id)
