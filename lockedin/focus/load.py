"""Training load: a stress score per activity, then fitness (CTL), fatigue (ATL) and form (TSB) per Brussels day.

Rides with power and an FTP use their power TSS. Runs, swims and rides without power use hrTSS: Banister's
TRIMP normalised so an hour at lactate-threshold HR is 100 (TrainingPeaks' definition). Gym sessions and
endurance sessions with nothing to measure get a flat, labelled estimate per hour.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import exp

from sqlalchemy import Connection, text

from lockedin.focus.sessions import COUNTED_SQL
from lockedin.focus.zones import max_hr_at
from lockedin.timeutil import TZ

CTL_DAYS, ATL_DAYS = 42, 7     # Coggan's Performance Manager time constants
SEED_DAYS = 90                 # history run in before the first day shown, so fitness doesn't start at zero
LTHR_OF_MAX = 0.89             # lactate-threshold HR ≈ 89% of max HR (Friel's field estimates sit at 85–92%)
RESTING_HR_DEFAULT = 60        # when the owner hasn't set one; it only shifts the TRIMP curve a little
TRIMP_K = {"male": 1.92, "female": 1.67}  # Banister 1991; unknown sex uses the male curve
HR_MAX_DT_S = 60               # a longer gap between HR samples is a pause, not more of the same effort
GYM_TSS_PER_HOUR = 40.0        # estimate: lifting with rests ≈ an easy endurance hour (IF ≈ 0.63)
UNMEASURED_IF = 0.7            # a run/ride/swim with no HR or power: assumed moderate endurance (49/h)
ENDURANCE = ("bike", "run", "swim")


def _trimp_weight(hr: float, max_hr: float, resting_hr: float, k: float) -> float:
    reserve = min(1.0, max(0.0, (hr - resting_hr) / (max_hr - resting_hr)))
    return reserve * 0.64 * exp(k * reserve)


def hr_tss(hr: list | None, t_offset: list | None, avg_hr: float | None, seconds: float, *, max_hr: float,
           resting_hr: float, sex: str | None) -> float | None:
    """TRIMP rate over the stream (time-weighted, so sparse samples are fine), else at the average HR,
    for the moving time, against the rate at LTHR."""
    k = TRIMP_K.get(sex or "", TRIMP_K["male"])
    rate = None
    if hr and t_offset and any(hr):
        total = weighted = 0.0
        for i, h in enumerate(hr):
            if not h:
                continue
            dt = min(HR_MAX_DT_S, t_offset[i + 1] - t_offset[i]) if i + 1 < len(t_offset) else 1
            if dt > 0:
                total += dt
                weighted += dt * _trimp_weight(h, max_hr, resting_hr, k)
        rate = weighted / total if total else None
    if rate is None and avg_hr:
        rate = _trimp_weight(avg_hr, max_hr, resting_hr, k)
    if rate is None:
        return None
    return seconds / 3600 * rate / _trimp_weight(LTHR_OF_MAX * max_hr, max_hr, resting_hr, k) * 100


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time(), TZ)


def activity_loads(conn: Connection, since: datetime, until: datetime) -> dict[date, float]:
    """Summed load per Brussels day for counted activities in [since, until]; days without load are left out."""
    rows = conn.execute(text(
        f"select id, sport, start_at, coalesce(moving_s, duration_s) as seconds, tss, avg_hr from activities "
        f"where {COUNTED_SQL} and start_at >= :since and start_at <= :until order by start_at"
    ), {"since": since, "until": until}).all()
    if not rows:
        return {}
    p = conn.execute(text("select resting_hr_override, sex from profile where id = 1")).one()
    max_hr = max_hr_at(conn, until)
    by_hr = [r.id for r in rows if r.sport != "gym" and r.tss is None] if max_hr else []
    streams = {s.activity_id: s for s in conn.execute(
        text("select activity_id, t_offset, hr from activity_streams where activity_id = any(:ids) and hr is not null"),
        {"ids": by_hr})}
    out: dict[date, float] = defaultdict(float)
    for r in rows:
        if r.tss is not None:
            load = r.tss
        elif r.sport == "gym":
            load = r.seconds / 3600 * GYM_TSS_PER_HOUR
        else:
            s = streams.get(r.id)
            load = hr_tss(s.hr if s else None, s.t_offset if s else None, r.avg_hr, r.seconds, max_hr=max_hr,
                          resting_hr=p.resting_hr_override or RESTING_HR_DEFAULT, sex=p.sex) if max_hr else None
            if load is None and r.sport in ENDURANCE:
                load = r.seconds / 3600 * UNMEASURED_IF ** 2 * 100
        if load:
            out[r.start_at.astimezone(TZ).date()] += load
    return dict(out)


def pmc(loads: dict[date, float], first: date, last: date) -> list[dict]:
    """Exponentially weighted fitness and fatigue from zero on `first`; form is yesterday's fitness − fatigue."""
    out = []
    fitness = fatigue = 0.0
    d = first
    while d <= last:
        load = loads.get(d, 0.0)
        form = fitness - fatigue
        fitness += (load - fitness) / CTL_DAYS
        fatigue += (load - fatigue) / ATL_DAYS
        out.append({"day": d, "load": load, "fitness": fitness, "fatigue": fatigue, "form": form})
        d += timedelta(days=1)
    return out


def training_load(conn: Connection, now: datetime, days: int = 180) -> dict:
    """The last `days` Brussels days, oldest first, every day present, numbers to one decimal."""
    today = now.astimezone(TZ).date()
    first = today - timedelta(days=days - 1)
    seed = first - timedelta(days=SEED_DAYS)
    rows = [r for r in pmc(activity_loads(conn, _day_start(seed), now), seed, today) if r["day"] >= first]
    rows = [{"day": r["day"], **{k: round(float(r[k]), 1) for k in ("load", "fitness", "fatigue", "form")}}
            for r in rows]
    any_activity = conn.execute(text(f"select exists (select 1 from activities where {COUNTED_SQL})")).scalar()
    return {"days": rows,
            "today": {k: rows[-1][k] for k in ("fitness", "fatigue", "form")} if any_activity else None}
