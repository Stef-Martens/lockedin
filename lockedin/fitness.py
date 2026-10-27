from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Connection, text

from lockedin.fit.metrics import training_stress
from lockedin.timeutil import TZ

FTP_FROM_20MIN = 0.95
FTP_LOOKBACK = timedelta(days=90)


class EstimatedFtp(float):
    """An FTP estimated from rides, not known from Zwift or the owner: fine for load, too rough to judge intervals."""


@dataclass
class KnownFtp:
    w: int
    source: str  # 'owner' | 'zwift'
    since: date | None


def known_ftp(conn: Connection, on: datetime) -> KnownFtp | None:
    """The FTP Zwift or the owner gave for that Brussels day; the newer of the two wins.

    Zwift's: the latest reading on/before the day, or its earliest one for days before Zwift said anything, so
    every ride sits on Zwift's scale. The owner's entry counts from its day until a newer Zwift reading; an
    empty entry hands back to Zwift. With no history at all, a bare profile override counts for every day.
    """
    d = on.astimezone(TZ).date()
    rows = conn.execute(text("select effective_from, ftp, source from ftp_history order by effective_from")).all()
    if not rows:
        override = conn.execute(text("select ftp_override from profile where id = 1")).scalar()
        return KnownFtp(override, "owner", None) if override else None
    zwift = [r for r in rows if r.source == "zwift" and r.ftp]
    z = next((r for r in reversed(zwift) if r.effective_from <= d), None)
    owner = next((r for r in reversed(rows) if r.source == "owner" and r.effective_from <= d), None)
    if owner and owner.ftp and (z is None or owner.effective_from >= z.effective_from):
        return KnownFtp(owner.ftp, "owner", owner.effective_from)
    z = z or (zwift[0] if zwift else None)
    return KnownFtp(z.ftp, "zwift", z.effective_from) if z else None


def known_ftp_at(conn: Connection, on: datetime) -> float | None:
    k = known_ftp(conn, on)
    return float(k.w) if k else None


def ftp_at(conn: Connection, on: datetime) -> float | None:
    """FTP in effect at a moment: Zwift's or the owner's, else 95% of the best 20-min power in the 90 days before.

    Strictly before: a ride never sets the FTP it is measured against.
    """
    known = known_ftp_at(conn, on)
    if known:
        return known
    best = conn.execute(text(
        "select max(best_20m_power) from activities "
        "where sport = 'bike' and superseded_by is null and start_at > :since and start_at < :on"
    ), {"since": on - FTP_LOOKBACK, "on": on}).scalar()
    return EstimatedFtp(FTP_FROM_20MIN * best) if best else None


def record_zwift_ftp(conn: Connection, day: date, ftp: int, activity_id: int | None = None) -> bool:
    """Zwift's FTP as of `day`; rides it now covers are rescored. False when it changes nothing."""
    before = known_ftp_at(conn, _day_start(day))
    earliest = conn.execute(text(
        "select min(effective_from) from ftp_history where source = 'zwift' and ftp is not null")).scalar()
    conn.execute(text(
        "insert into ftp_history (effective_from, ftp, source, activity_id) values (:d, :ftp, 'zwift', :a) "
        "on conflict (effective_from, source) do update set ftp = excluded.ftp, "
        "activity_id = coalesce(excluded.activity_id, ftp_history.activity_id), created_at = now()"
    ), {"d": day, "ftp": ftp, "a": activity_id})
    if before == ftp:
        return False
    # Zwift's first reading also covers every ride before it.
    recompute_training_load(conn, since=None if earliest is None or day < earliest else _day_start(day))
    return True


def set_ftp(conn: Connection, ftp: int | None, now: datetime) -> None:
    """The owner's FTP from today (Brussels) on, until Zwift says otherwise; None hands back to Zwift or the estimate.
    Rides from today are rescored, earlier ones keep theirs."""
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
        "insert into ftp_history (effective_from, ftp, source) values (:d, :ftp, 'owner') "
        "on conflict (effective_from, source) do update set ftp = excluded.ftp, created_at = now()"
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
