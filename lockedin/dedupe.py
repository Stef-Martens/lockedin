"""Keep one record per real session when the Apple Watch (via HealthFit) also recorded it.

A HealthFit workout overlapping a Zwift ride or a Hevy workout by more than half of the
shorter one is marked superseded by it. If the Zwift ride has no heart rate, the Watch's
heart rate is copied onto it. Works whichever file arrives first.
"""

from bisect import bisect_left

from sqlalchemy import Connection, text

PRIMARY_SOURCES = ("zwift", "hevy")
HR_MATCH_WINDOW_S = 5


def _overlaps(a, b) -> bool:
    shared = (min(a.end_at, b.end_at) - max(a.start_at, b.start_at)).total_seconds()
    shorter = min((a.end_at - a.start_at).total_seconds(), (b.end_at - b.start_at).total_seconds())
    return shared > 0.5 * shorter


def _get(conn: Connection, activity_id: int):
    return conn.execute(text("select * from activities where id = :i"), {"i": activity_id}).one()


def resolve_overlaps(conn: Connection, activity_id: int) -> None:
    a = _get(conn, activity_id)
    others = conn.execute(text(
        "select * from activities where id <> :i and start_at < :end and end_at > :start"
    ), {"i": a.id, "start": a.start_at, "end": a.end_at}).all()

    if a.source == "healthfit":
        primaries = [o for o in others if o.source in PRIMARY_SOURCES and _overlaps(a, o)]
        if not primaries:
            return
        preferred = "zwift" if a.sport == "bike" else "hevy"
        primary = sorted(primaries, key=lambda o: o.source != preferred)[0]
        _supersede(conn, watch=a, primary=primary)
    elif a.source in PRIMARY_SOURCES:
        for o in others:
            if o.source == "healthfit" and o.superseded_by is None and _overlaps(a, o):
                _supersede(conn, watch=o, primary=a)


def _supersede(conn: Connection, *, watch, primary) -> None:
    conn.execute(text("update activities set superseded_by = :p where id = :w"), {"p": primary.id, "w": watch.id})
    if primary.source == "zwift" and primary.avg_hr is None and watch.avg_hr is not None:
        _merge_hr(conn, watch=watch, ride=primary)


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


