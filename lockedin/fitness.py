from datetime import datetime, timedelta

from sqlalchemy import Connection, text

FTP_FROM_20MIN = 0.95
FTP_LOOKBACK = timedelta(days=90)


def ftp_at(conn: Connection, on: datetime) -> float | None:
    """FTP in effect on a date: the profile override, else 95% of the best 20-min power in the prior 90 days."""
    override = conn.execute(text("select ftp_override from profile where id = 1")).scalar()
    if override:
        return float(override)
    best = conn.execute(text(
        "select max(best_20m_power) from activities "
        "where sport = 'bike' and superseded_by is null and start_at > :since and start_at <= :on"
    ), {"since": on - FTP_LOOKBACK, "on": on}).scalar()
    return FTP_FROM_20MIN * best if best else None
