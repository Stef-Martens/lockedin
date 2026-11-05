import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Connection, text

from lockedin.agenda.zwift_ftp import learn_from_ride
from lockedin.dedupe import resolve_overlaps
from lockedin.fit.metrics import best_avg_power, normalized_power
from lockedin.fit.parse import EmptyActivity, FitParseError, ParsedFit, parse_fit_activities
from lockedin.fitness import recompute_training_load
from lockedin.verdict.store import NEW_FOR

log = logging.getLogger(__name__)

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


def _set_laps(conn: Connection, where: str, params: dict, laps: list[dict]) -> None:
    """Give the activity picked by `where` its laps if it has none. A lap list with workout steps replaces the
    saved verdict, which was written without them, unless the workout is too old to get a new one."""
    row = conn.execute(text(f"update activities set laps = cast(:l as jsonb) where laps is null and {where} "
                            "returning id, start_at"), {**params, "l": json.dumps(laps)}).first()
    if row and any(lap["step_index"] is not None for lap in laps) and datetime.now(UTC) - row.start_at <= NEW_FOR:
        conn.execute(text("delete from workout_verdicts where activity_id = :i"), {"i": row.id})


def _fill_laps(conn: Connection, sha: str, data: bytes, activity_id: int | None = None) -> None:
    """Activities imported before laps were kept get them from the file when it is uploaded again. A re-export
    with other bytes is matched by `activity_id`, the activity it was attached to. Never raises: the upload is
    a duplicate either way."""
    try:
        savepoint = conn.begin_nested()
    except Exception:
        log.warning("Could not fill in the laps of %s", sha, exc_info=True)
        return
    try:
        if conn.execute(text(
            "select 1 from activities where laps is null and (source_ref = :s or source_ref like :s || '#%' "
            "or id = :a) limit 1"
        ), {"s": sha, "a": activity_id}).first():
            for i, f in enumerate(parse_fit_activities(data)):
                ref = sha if i == 0 else f"{sha}#{i + 1}"
                if conn.execute(text("select 1 from activities where source_ref = :r"), {"r": ref}).first():
                    _set_laps(conn, "source_ref = :ref", {"ref": ref}, f.laps)
                elif i == 0 and activity_id is not None:
                    _set_laps(conn, "id = :id", {"id": activity_id}, f.laps)
    except Exception:
        savepoint.rollback()
        log.warning("Could not fill in the laps of %s", sha, exc_info=True)
        return
    savepoint.commit()


def import_fit(conn: Connection, data: bytes, filename: str, source_hint: Source | None) -> FitImportResult:
    sha = hashlib.sha256(data).hexdigest()
    existing = conn.execute(text(
        "select activity_id, parse_status, error, unreadable from fit_files where sha256 = :s"), {"s": sha}).first()
    if existing and existing.parse_status in ("ok", "empty"):
        if existing.parse_status == "ok":
            _fill_laps(conn, sha, data, existing.activity_id)
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
        for (activity_id, is_new), f in zip(stored, legs):
            if is_new and source == "zwift" and f.sport == "bike":
                learn_from_ride(conn, activity_id)  # one of the app's workouts in ERG tells Zwift's FTP
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
        _set_laps(conn, "id = :id", {"id": same}, f.laps)  # which may be the first file this session's laps come from
        return same, False
    pace_km, pace_100 = _paces(f)
    activity_id = conn.execute(text(
        "insert into activities (source, source_ref, sport, sub_type, start_at, end_at, duration_s, moving_s, "
        "distance_m, elevation_m, avg_hr, max_hr, calories, avg_power, max_power, avg_cadence, "
        "avg_pace_s_per_km, swim_pace_s_per_100m, swim_lengths, swim_strokes, pool_length_m, laps) "
        "values (:source, :ref, :sport, :sub_type, :start_at, :end_at, :duration_s, :moving_s, "
        ":distance_m, :elevation_m, :avg_hr, :max_hr, :calories, :avg_power, :max_power, :avg_cadence, "
        ":pace_km, :pace_100, :swim_lengths, :swim_strokes, :pool_length_m, cast(:laps as jsonb)) "
        "on conflict (source, source_ref) do update set source_ref = excluded.source_ref returning id"
    ), {
        "source": source, "ref": ref, "sport": f.sport, "sub_type": f.sub_type, "start_at": f.start_at,
        "end_at": f.end_at, "duration_s": f.duration_s, "moving_s": f.moving_s, "distance_m": f.distance_m,
        "elevation_m": f.elevation_m, "avg_hr": f.avg_hr, "max_hr": f.max_hr, "calories": f.calories,
        "avg_power": f.avg_power, "max_power": f.max_power, "avg_cadence": f.avg_cadence,
        "pace_km": pace_km, "pace_100": pace_100, "swim_lengths": f.swim_lengths,
        "swim_strokes": f.swim_strokes, "pool_length_m": f.pool_length_m, "laps": json.dumps(f.laps),
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
