from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

# Sessions that count toward totals, streaks, mix, wins and trends: no Watch duplicates, no casual walks.
COUNTED_SQL = "superseded_by is null and coalesce(sub_type, '') not like 'walking%'"

FIELDS = ("id", "sport", "sub_type", "source", "start_at", "duration_s", "distance_m", "avg_hr", "max_hr", "np",
          "avg_power", "best_20m_power", "avg_pace_s_per_km", "swim_pace_s_per_100m")


@dataclass
class Session:
    id: int
    sport: str
    sub_type: str | None
    source: str
    start_at: datetime
    duration_s: int
    distance_m: float | None
    avg_hr: int | None
    max_hr: int | None
    np: float | None
    avg_power: int | None
    best_20m_power: float | None
    avg_pace_s_per_km: float | None
    swim_pace_s_per_100m: float | None


def counted_sessions(conn: Connection, since: datetime, until: datetime, sport: str | None = None) -> list[Session]:
    rows = conn.execute(text(
        f"select {', '.join(FIELDS)} from activities where {COUNTED_SQL} "
        "and start_at > :since and start_at <= :until and (cast(:sport as text) is null or sport = :sport) "
        "order by start_at"
    ), {"since": since, "until": until, "sport": sport})
    return [Session(**r._mapping) for r in rows]
