from datetime import datetime, timedelta

from sqlalchemy import Connection, text

from lockedin.fit.metrics import training_stress

FTP_FROM_20MIN = 0.95
FTP_LOOKBACK = timedelta(days=90)


def ftp_at(conn: Connection, on: datetime) -> float | None:
    """FTP in effect at a moment: the profile override, else 95% of the best 20-min power in the 90 days before.

    Strictly before: a ride never sets the FTP it is measured against.
    """
    override = conn.execute(text("select ftp_override from profile where id = 1")).scalar()
    if override:
        return float(override)
    best = conn.execute(text(
        "select max(best_20m_power) from activities "
        "where sport = 'bike' and superseded_by is null and start_at > :since and start_at < :on"
    ), {"since": on - FTP_LOOKBACK, "on": on}).scalar()
    return FTP_FROM_20MIN * best if best else None


def recompute_training_load(conn: Connection, since: datetime | None = None) -> None:
    """Refresh IF/TSS for rides from `since` on (all when None), oldest first, since each ride feeds later FTPs."""
    rides = conn.execute(text(
        "select id, start_at, duration_s, np from activities "
        "where sport = 'bike' and np is not null and (cast(:since as timestamptz) is null or start_at >= :since) "
        "order by start_at"
    ), {"since": since}).all()
    for r in rides:
        ftp = ftp_at(conn, r.start_at)
        if_, tss = training_stress(r.duration_s, r.np, ftp) if ftp else (None, None)
        conn.execute(text("update activities set if_ = :if_, tss = :tss where id = :i"), {"if_": if_, "tss": tss, "i": r.id})
