from datetime import date, datetime, time, timedelta

from sqlalchemy import Connection, text

from lockedin.fit.metrics import training_stress
from lockedin.timeutil import TZ

FTP_FROM_20MIN = 0.95
FTP_LOOKBACK = timedelta(days=90)


class EstimatedFtp(float):
    """An FTP estimated from rides, not entered by the owner: fine for load, too rough to judge intervals against."""


def owner_ftp_at(conn: Connection, on: datetime) -> float | None:
    """The FTP the owner entered for that Brussels day: the latest ftp_history row on/before it (an empty row clears it).

    With no history at all, a bare profile override still counts for every day, as before history existed.
    """
    r = conn.execute(text(
        "select (select ftp from ftp_history where effective_from <= :d order by effective_from desc limit 1) as ftp, "
        "exists (select 1 from ftp_history) as has_history, (select ftp_override from profile where id = 1) as override"
    ), {"d": on.astimezone(TZ).date()}).one()
    ftp = r.ftp if r.has_history else r.override
    return float(ftp) if ftp else None


def ftp_at(conn: Connection, on: datetime) -> float | None:
    """FTP in effect at a moment: the owner's, else 95% of the best 20-min power in the 90 days before.

    Strictly before: a ride never sets the FTP it is measured against.
    """
    owner = owner_ftp_at(conn, on)
    if owner:
        return owner
    best = conn.execute(text(
        "select max(best_20m_power) from activities "
        "where sport = 'bike' and superseded_by is null and start_at > :since and start_at < :on"
    ), {"since": on - FTP_LOOKBACK, "on": on}).scalar()
    return EstimatedFtp(FTP_FROM_20MIN * best) if best else None


def set_ftp(conn: Connection, ftp: int | None, now: datetime) -> None:
    """The owner's FTP from today (Brussels) on; rides from today are rescored, earlier ones keep theirs."""
    today = now.astimezone(TZ).date()
    if not conn.execute(text("select exists (select 1 from ftp_history)")).scalar():
        # A bare override from before history scored every ride so far: keep it for them.
        conn.execute(text(
            "insert into ftp_history (effective_from, ftp) "
            "select least(:today, coalesce((select min((start_at at time zone 'Europe/Brussels')::date) from activities), "
            ":today)), ftp_override from profile where id = 1 and ftp_override is not null "
            "on conflict do nothing"
        ), {"today": today})
    conn.execute(text(
        "insert into ftp_history (effective_from, ftp) values (:d, :ftp) "
        "on conflict (effective_from) do update set ftp = excluded.ftp, created_at = now()"
    ), {"d": today, "ftp": ftp})
    conn.execute(text("update profile set ftp_override = :ftp, updated_at = now() where id = 1"), {"ftp": ftp})
    recompute_training_load(conn, since=_day_start(today))


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time(), TZ)


def recompute_training_load(conn: Connection, since: datetime | None = None) -> None:
    """Refresh IF/TSS for rides from `since` on (all when None), oldest first, since each ride feeds later FTPs.

    TSS is over moving (timer) time: a paused stretch is no training.
    """
    rides = conn.execute(text(
        "select id, start_at, coalesce(moving_s, duration_s) as seconds, np from activities "
        "where sport = 'bike' and np is not null and (cast(:since as timestamptz) is null or start_at >= :since) "
        "order by start_at"
    ), {"since": since}).all()
    for r in rides:
        ftp = ftp_at(conn, r.start_at)
        if_, tss = training_stress(r.seconds, r.np, ftp) if ftp else (None, None)
        conn.execute(text("update activities set if_ = :if_, tss = :tss where id = :i"), {"if_": if_, "tss": tss, "i": r.id})
