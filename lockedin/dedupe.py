"""Keep one record per real session when the Apple Watch (via HealthFit) also recorded it.

A HealthFit workout overlapping a Zwift ride or run (of the same sport) or a Hevy workout by more
than half of the shorter one is marked superseded by it. If the Zwift activity has no heart rate,
the heart rate of the Watch file sharing the most time with it is copied onto it. Works whichever
file arrives first, and is decided again when a Hevy workout moves.
"""

from bisect import bisect_left

from sqlalchemy import Connection, text

PRIMARY_SOURCES = ("zwift", "hevy")
HR_MATCH_WINDOW_S = 5


def _replaces(primary) -> tuple[str, ...]:
    """Which Watch workouts a primary can stand in for: a run or ride inside a gym session stays a run or
    ride, and a Zwift run replaces the Watch's indoor run, not a ride."""
    return ("other",) if primary.source == "hevy" else (primary.sport, "other")


def _shared_s(a, b) -> float:
    return (min(a.end_at, b.end_at) - max(a.start_at, b.start_at)).total_seconds()


def _overlaps(a, b) -> bool:
    shorter = min((a.end_at - a.start_at).total_seconds(), (b.end_at - b.start_at).total_seconds())
    return _shared_s(a, b) > 0.5 * shorter


def _get(conn: Connection, activity_id: int):
    return conn.execute(text("select * from activities where id = :i"), {"i": activity_id}).one()


def resolve_overlaps(conn: Connection, activity_id: int) -> None:
    a = _get(conn, activity_id)
    if a.source == "healthfit":
        _resolve_watch(conn, a)
    elif a.source in PRIMARY_SOURCES:
        # It may have moved (times edited in Hevy): let go of the Watch workouts it stood in for and decide again.
        freed = conn.execute(text("update activities set superseded_by = null where superseded_by = :i returning id"),
                             {"i": a.id}).scalars().all()
        overlapping = conn.execute(text(
            "select id from activities where source = 'healthfit' and superseded_by is null "
            "and start_at < :end and end_at > :start"
        ), {"start": a.start_at, "end": a.end_at}).scalars().all()
        for wid in sorted({*freed, *overlapping}):
            _resolve_watch(conn, _get(conn, wid))


def _resolve_watch(conn: Connection, watch) -> None:
    primaries = [o for o in conn.execute(text(
        "select * from activities where source = any(:src) and start_at < :end and end_at > :start"
    ), {"src": list(PRIMARY_SOURCES), "start": watch.start_at, "end": watch.end_at})
        if watch.sport in _replaces(o) and _overlaps(watch, o)]
    if not primaries:
        return
    preferred = "hevy" if watch.sport == "other" else "zwift"
    primary = min(primaries, key=lambda o: (o.source != preferred, -_shared_s(watch, o), o.id))
    conn.execute(text("update activities set superseded_by = :p where id = :w"), {"p": primary.id, "w": watch.id})
    if primary.source == "zwift":
        _borrow_hr(conn, primary.id)


def _borrow_hr(conn: Connection, ride_id: int) -> None:
    """A Zwift ride without its own heart rate takes it from the Watch file it shares the most time with."""
    ride = _get(conn, ride_id)
    if ride.avg_hr is not None and ride.hr_merged_from is None:
        return  # its own strap
    watches = conn.execute(text("select * from activities where superseded_by = :r and avg_hr is not null"),
                           {"r": ride.id}).all()
    if watches:
        best = min(watches, key=lambda w: (-_shared_s(ride, w), w.id))
        if best.id != ride.hr_merged_from:
            _merge_hr(conn, watch=best, ride=ride)


def _merge_hr(conn: Connection, *, watch, ride) -> None:
    conn.execute(text(
        "update activities set avg_hr = :avg, max_hr = :max, hr_merged_from = :w where id = :r"
    ), {"avg": watch.avg_hr, "max": watch.max_hr, "w": watch.id, "r": ride.id})

    ws = conn.execute(text("select t_offset, hr from activity_streams where activity_id = :i"), {"i": watch.id}).first()
    rs = conn.execute(text("select t_offset from activity_streams where activity_id = :i"), {"i": ride.id}).first()
    if not ws or not rs:
        return
    shift = (ride.start_at - watch.start_at).total_seconds()  # ride t=0 is watch t=shift
    samples = [(t, h) for t, h in zip(ws.t_offset, ws.hr) if h is not None]
    times = [t for t, _ in samples]
    merged: list[int | None] = []
    for t in rs.t_offset:
        target = t + shift
        i = bisect_left(times, target)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(times) and abs(times[j] - target) <= HR_MATCH_WINDOW_S:
                if best is None or abs(times[j] - target) < abs(times[best] - target):
                    best = j
        merged.append(samples[best][1] if best is not None else None)
    conn.execute(text("update activity_streams set hr = cast(:hr as smallint[]) where activity_id = :i"),
                 {"hr": merged, "i": ride.id})
    if merged and any(h is not None for h in merged):
        present = [h for h in merged if h is not None]
        conn.execute(text("update activities set avg_hr = :avg, max_hr = :max where id = :r"),
                     {"avg": round(sum(present) / len(present)), "max": max(present), "r": ride.id})


