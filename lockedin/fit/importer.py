import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection, text

from lockedin.dedupe import resolve_overlaps
from lockedin.fit.metrics import best_avg_power, normalized_power
from lockedin.fit.parse import EmptyActivity, FitParseError, ParsedFit, parse_fit_activities
from lockedin.fitness import recompute_training_load

Source = Literal["zwift", "healthfit"]


@dataclass
class FitImportResult:
    status: Literal["imported", "duplicate", "empty", "error"]
    sha256: str
    activity_id: int | None = None  # a multisport file's first leg
    error: str | None = None
    already_failed: bool = False  # these exact bytes were unreadable before, so weren't parsed again


def known_hashes(conn: Connection, hashes: list[str]) -> set[str]:
    if not hashes:
        return set()
    rows = conn.execute(text("select sha256 from fit_files where parse_status in ('ok', 'empty') and sha256 = any(:h)"),
                        {"h": list(hashes)}).scalars()
    return set(rows)


def _record_file(conn: Connection, sha: str, filename: str, source: str | None, activity_id: int | None,
                 error: str | None, status: str | None = None, unreadable: bool = False) -> None:
    conn.execute(text(
        "insert into fit_files (sha256, filename, source, activity_id, parse_status, error, unreadable) "
        "values (:s, :f, :src, :a, :st, :e, :u) "
        "on conflict (sha256) do update set filename = excluded.filename, source = excluded.source, "
        "activity_id = excluded.activity_id, parse_status = excluded.parse_status, error = excluded.error, "
        "unreadable = excluded.unreadable, uploaded_at = now()"
    ), {"s": sha, "f": filename, "src": source, "a": activity_id,
        "st": status or ("error" if error else "ok"), "e": error, "u": unreadable})


def _paces(f: ParsedFit) -> tuple[float | None, float | None]:
    secs = f.moving_s or f.duration_s
    if not f.distance_m or not secs:
        return None, None
    if f.sport == "run":
        return secs / (f.distance_m / 1000), None
    if f.sport == "swim":  # in a pool, the time in active lengths: rests at the wall don't slow the pace
        return None, (f.swim_active_s or secs) / (f.distance_m / 100)
    return None, None


SAME_START_S = 60


def _same_session(conn: Connection, source: str, f: ParsedFit) -> int | None:
    return conn.execute(text(
        "select id from activities where source = :src and sport = :sport "
        "and abs(extract(epoch from start_at - :start)) <= :tol "
        "and abs(duration_s - :dur) <= greatest(:tol, 0.1 * :dur) order by id limit 1"
    ), {"src": source, "sport": f.sport, "start": f.start_at, "dur": f.duration_s, "tol": SAME_START_S}).scalar()


def import_fit(conn: Connection, data: bytes, filename: str, source_hint: Source | None) -> FitImportResult:
    sha = hashlib.sha256(data).hexdigest()
    existing = conn.execute(text(
        "select activity_id, parse_status, error, unreadable from fit_files where sha256 = :s"), {"s": sha}).first()
    if existing and existing.parse_status in ("ok", "empty"):
        return FitImportResult("duplicate", sha, existing.activity_id)
    if existing and existing.unreadable:  # the same bytes get the same answer; no need to parse them again
        return FitImportResult("error", sha, error=existing.error, already_failed=True)

    try:
        legs = parse_fit_activities(data)
    except EmptyActivity:
        _record_file(conn, sha, filename, source_hint, None, None, status="empty")
        return FitImportResult("empty", sha)
    except FitParseError as e:
        _record_file(conn, sha, filename, source_hint, None, str(e), unreadable=True)
        return FitImportResult("error", sha, error=str(e))

    source = source_hint or ("zwift" if legs[0].manufacturer == "zwift" else "healthfit")
    savepoint = conn.begin_nested()
    try:
        # A multisport file is one activity per leg; the first keeps the file's hash as its reference.
        stored = [_store(conn, sha if i == 0 else f"{sha}#{i + 1}", filename, source, f) for i, f in enumerate(legs)]
        _record_file(conn, sha, filename, source, stored[0][0], None)
        new = any(is_new for _, is_new in stored)
        rides = [f.start_at for f in legs if f.sport == "bike"]
        if new and rides:
            recompute_training_load(conn, since=min(rides))  # these rides and later ones whose FTP they may raise
    except Exception as e:  # odd real-world files must come back as an error, never a 500
        savepoint.rollback()
        msg = f"Could not import this file: {e}"
        _record_file(conn, sha, filename, source, None, msg)
        return FitImportResult("error", sha, error=msg)
    savepoint.commit()
    return FitImportResult("imported" if new else "duplicate", sha, stored[0][0])


def _store(conn: Connection, ref: str, filename: str, source: str, f: ParsedFit) -> tuple[int, bool]:
    """(activity id, whether it is new) for one activity of a file."""
    same = _same_session(conn, source, f)
    if same is not None:  # a re-export of a session we already have, with different bytes
        return same, False
    pace_km, pace_100 = _paces(f)
    activity_id = conn.execute(text(
        "insert into activities (source, source_ref, sport, sub_type, start_at, end_at, duration_s, moving_s, "
        "distance_m, elevation_m, avg_hr, max_hr, calories, avg_power, max_power, avg_cadence, "
        "avg_pace_s_per_km, swim_pace_s_per_100m, swim_lengths, swim_strokes, pool_length_m) "
        "values (:source, :ref, :sport, :sub_type, :start_at, :end_at, :duration_s, :moving_s, "
        ":distance_m, :elevation_m, :avg_hr, :max_hr, :calories, :avg_power, :max_power, :avg_cadence, "
        ":pace_km, :pace_100, :swim_lengths, :swim_strokes, :pool_length_m) "
        "on conflict (source, source_ref) do update set source_ref = excluded.source_ref returning id"
    ), {
        "source": source, "ref": ref, "sport": f.sport, "sub_type": f.sub_type, "start_at": f.start_at,
        "end_at": f.end_at, "duration_s": f.duration_s, "moving_s": f.moving_s, "distance_m": f.distance_m,
        "elevation_m": f.elevation_m, "avg_hr": f.avg_hr, "max_hr": f.max_hr, "calories": f.calories,
        "avg_power": f.avg_power, "max_power": f.max_power, "avg_cadence": f.avg_cadence,
        "pace_km": pace_km, "pace_100": pace_100, "swim_lengths": f.swim_lengths,
        "swim_strokes": f.swim_strokes, "pool_length_m": f.pool_length_m,
    }).scalar_one()

    s = f.streams
    conn.execute(text(
        "insert into activity_streams (activity_id, t_offset, power, hr, cadence, speed, altitude, distance) "
        "values (:i, cast(:t as integer[]), cast(:p as smallint[]), cast(:hr as smallint[]), "
        "cast(:c as smallint[]), cast(:sp as real[]), cast(:al as real[]), cast(:d as real[])) "
        "on conflict (activity_id) do nothing"
    ), {"i": activity_id, "t": s.t_offset, "p": s.power, "hr": s.hr, "c": s.cadence, "sp": s.speed,
        "al": s.altitude, "d": s.distance})

    if f.sport == "bike":
        np_ = normalized_power(s.power, s.t_offset)
        best20 = best_avg_power(s.power, s.t_offset, 1200)
        conn.execute(text("update activities set np = :np, best_20m_power = :b where id = :i"),
                     {"np": np_, "b": best20, "i": activity_id})

    resolve_overlaps(conn, activity_id)
    conn.execute(text("insert into import_log (source, summary) values (:s, cast(:j as jsonb))"),
                 {"s": source, "j": json.dumps({"filename": filename, "activity_id": activity_id, "sport": f.sport})})
    return activity_id, True
