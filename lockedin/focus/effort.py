"""Label each run/ride/swim easy, steady, hard or long from time in zones (or averages when there's no stream)."""

from datetime import datetime, timedelta
from statistics import median
from typing import Literal

from sqlalchemy import Connection, text

from lockedin.fit.metrics import rolling_means
from lockedin.fitness import ftp_at
from lockedin.focus.sessions import Session, counted_sessions
from lockedin.focus.zones import HR_ZONE_STARTS, POWER_ZONE_STARTS, hr_zone, max_hr_at, power_zone

Effort = Literal["easy", "steady", "hard", "long"]

HARD_FRAC = 0.15
EASY_FRAC = 0.75
LONG_EASY_FRAC = 0.6
LONG_FACTOR = 1.5
MEDIAN_DAYS = 56
MEDIAN_MIN_SESSIONS = 3
EASY_BELOW_ZONE, HARD_FROM_ZONE = 3, 4  # zones 1–2 easy, 4–5 hard: Seiler's three zones on the five
POWER_SMOOTH_S = 30  # as in NP: a few seconds' surge isn't time at that intensity


def _by_average(frac: float, starts: tuple[int, ...]) -> Effort:
    """A whole-session average judged on the same zone boundaries as time in zones."""
    if frac * 100 < starts[EASY_BELOW_ZONE - 1]:
        return "easy"
    return "hard" if frac * 100 >= starts[HARD_FROM_ZONE - 1] else "steady"


def classify_effort(s: Session, *, power: list | None, hr: list | None, ftp: float | None, max_hr: int | None,
                    median_duration_s: float | None, median_swim_pace: float | None,
                    t_offset: list | None = None) -> Effort | None:
    zones: list[int] | None = None
    if s.sport == "bike" and ftp and power and any(power):
        smooth = rolling_means(power, t_offset or range(len(power)), POWER_SMOOTH_S)
        zones = [power_zone(p, ftp) for p in smooth if p]
    elif max_hr and hr and any(hr):
        zones = [hr_zone(h, max_hr) for h in hr if h]

    easy_frac = None
    if zones:
        easy_frac = sum(z < EASY_BELOW_ZONE for z in zones) / len(zones)
        hard_frac = sum(z >= HARD_FROM_ZONE for z in zones) / len(zones)
        base: Effort = "hard" if hard_frac >= HARD_FRAC else "easy" if easy_frac >= EASY_FRAC else "steady"
    elif s.sport == "bike" and s.np and ftp:
        base = _by_average(s.np / ftp, POWER_ZONE_STARTS)  # IF
    elif s.avg_hr and max_hr:
        base = _by_average(s.avg_hr / max_hr, HR_ZONE_STARTS)
    elif s.sport == "swim" and s.swim_pace_s_per_100m and median_swim_pace:
        ratio = s.swim_pace_s_per_100m / median_swim_pace  # lower pace = faster
        base = "hard" if ratio <= 0.95 else "easy" if ratio >= 1.05 else "steady"
    else:
        return None

    is_long = (base != "hard" and median_duration_s and s.duration_s >= LONG_FACTOR * median_duration_s
               and (easy_frac is None or easy_frac >= LONG_EASY_FRAC))
    return "long" if is_long else base


def _medians(conn: Connection, now: datetime, sport: str) -> tuple[float | None, float | None]:
    past = counted_sessions(conn, now - timedelta(days=MEDIAN_DAYS), now, sport)
    durations = [s.duration_s for s in past]
    paces = [s.swim_pace_s_per_100m for s in past if s.swim_pace_s_per_100m]
    return (median(durations) if len(durations) >= MEDIAN_MIN_SESSIONS else None,
            median(paces) if len(paces) >= MEDIAN_MIN_SESSIONS else None)


def effort_for_window(conn: Connection, now: datetime, days: int = 28,
                      sport: str | None = None) -> list[tuple[Session, Effort | None]]:
    sessions = [s for s in counted_sessions(conn, now - timedelta(days=days), now, sport) if s.sport in ("bike", "run", "swim")]
    if not sessions:
        return []
    max_hr = max_hr_at(conn, now)
    medians = {sp: _medians(conn, now, sp) for sp in {s.sport for s in sessions}}
    streams = {r.activity_id: r for r in conn.execute(
        text("select activity_id, t_offset, power, hr from activity_streams where activity_id = any(:ids)"),
        {"ids": [s.id for s in sessions]})}
    out = []
    for s in sessions:
        st = streams.get(s.id)
        med_dur, med_pace = medians[s.sport]
        out.append((s, classify_effort(
            s, power=st.power if st else None, hr=st.hr if st else None, t_offset=st.t_offset if st else None,
            ftp=ftp_at(conn, s.start_at) if s.sport == "bike" else None, max_hr=max_hr,
            median_duration_s=med_dur, median_swim_pace=med_pace)))
    return out
