"""Decode a FIT activity file (Zwift or HealthFit) into a summary plus per-second streams."""

import io
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import fitdecode

Sport = Literal["bike", "run", "swim", "other"]
SPORTS: dict[str, Sport] = {"cycling": "bike", "running": "run", "swimming": "swim"}
MIN_ACTIVITY_S = 60


class FitParseError(Exception):
    pass


class EmptyActivity(FitParseError):
    """A valid file with nothing in it, e.g. a Zwift ride started and quit within seconds."""


@dataclass
class Streams:
    t_offset: list[int] = field(default_factory=list)
    power: list[int | None] = field(default_factory=list)
    hr: list[int | None] = field(default_factory=list)
    cadence: list[int | None] = field(default_factory=list)
    speed: list[float | None] = field(default_factory=list)
    altitude: list[float | None] = field(default_factory=list)
    distance: list[float | None] = field(default_factory=list)


@dataclass
class ParsedFit:
    sport: Sport
    sub_type: str | None
    manufacturer: str | None
    start_at: datetime
    end_at: datetime
    duration_s: int
    moving_s: int | None
    distance_m: float | None
    elevation_m: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_power: int | None
    max_power: int | None
    avg_cadence: int | None
    calories: int | None
    pool_length_m: float | None
    swim_lengths: int | None
    swim_strokes: int | None
    streams: Streams
    swim_active_s: int | None = None  # pool swims: time in active lengths, i.e. without rest at the wall
    # One per lap the device recorded (a Watch workout has one per planned step); start_s is from the activity's start.
    laps: list[dict] = field(default_factory=list)


def _values(frame) -> dict:
    return {f.name: f.value for f in frame.fields if f.value is not None}


def _int(v) -> int | None:
    return None if v is None else int(round(v))


def _hr(v) -> int | None:
    """Zwift writes 0 when no heart-rate strap is paired; that means "no data", not 0 bpm."""
    v = _int(v)
    return v if v else None


def _lap_start_s(start, start_at: datetime) -> float | None:
    if not isinstance(start, datetime):  # one odd lap must not make the whole file unreadable
        return None
    return round((_aware(start) - start_at).total_seconds(), 1)


def _lap(values: dict, start_at: datetime) -> dict:
    speed = values.get("enhanced_avg_speed", values.get("avg_speed"))
    intensity, trigger = values.get("intensity"), values.get("lap_trigger")
    return {
        "start_s": _lap_start_s(values.get("start_time"), start_at),
        "timer_s": values.get("total_timer_time"),
        "elapsed_s": values.get("total_elapsed_time"),
        "distance_m": values.get("total_distance"),
        "avg_hr": _hr(values.get("avg_heart_rate")),
        "avg_speed": speed,
        "intensity": None if intensity is None else str(intensity),
        "trigger": None if trigger is None else str(trigger),
        "step_index": _int(values.get("wkt_step_index")),
    }


def _avg(xs: list) -> int | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs)) if xs else None


def _max(xs: list) -> int | None:
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def parse_fit(data: bytes) -> ParsedFit:
    """The file's first activity; see parse_fit_activities for multisport files."""
    return parse_fit_activities(data)[0]


def parse_fit_activities(data: bytes) -> list[ParsedFit]:
    """One activity per session: a multisport file (e.g. a bike-run brick) has a session per leg.
    Transitions and legs too short to count are left out."""
    try:
        return _parse(data)
    except FitParseError:
        raise
    except Exception as e:  # unexpected field values in real-world files
        raise FitParseError(f"Could not read FIT file: {e}") from e


def _parse(data: bytes) -> list[ParsedFit]:
    file_id: dict = {}
    sessions: list[dict] = []
    records: list[dict] = []
    lengths: list[dict] = []
    laps: list[dict] = []
    try:
        with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.RAISE) as fit:
            for frame in fit:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if frame.name == "file_id":
                    file_id = _values(frame)
                elif frame.name == "session":
                    sessions.append(_values(frame))
                elif frame.name == "record":
                    v = _values(frame)
                    if "timestamp" in v:
                        records.append(v)
                elif frame.name == "length":
                    lengths.append(_values(frame))
                elif frame.name == "lap":
                    laps.append(_values(frame))
    except Exception as e:  # fitdecode raises several types for truncated/garbage input
        raise FitParseError(f"Could not read FIT file: {e}") from e

    legs = sorted((s for s in sessions if "start_time" in s), key=lambda s: _aware(s["start_time"]))
    if len(legs) < 2:
        return [_activity(file_id, sessions[0] if sessions else {}, records, lengths, laps)]
    starts = [_aware(s["start_time"]) for s in legs]

    def leg(ts) -> int:  # the last leg started by then
        return max(bisect_right(starts, _aware(ts)) - 1, 0) if ts else 0

    parts: list[tuple[list, list, list]] = [([], [], []) for _ in legs]
    for r in records:
        parts[leg(r["timestamp"])][0].append(r)
    for ln in lengths:
        parts[leg(ln.get("start_time") or ln.get("timestamp"))][1].append(ln)
    for lap in laps:
        parts[leg(lap.get("start_time") or lap.get("timestamp"))][2].append(lap)
    out = []
    for s, (recs, lens, leg_laps) in zip(legs, parts):
        if str(s.get("sport")) == "transition":
            continue
        d0 = next((r["distance"] for r in recs if r.get("distance") is not None), None)
        if d0:  # some devices count distance on from the previous leg
            recs = [{**r, "distance": r["distance"] - d0} if r.get("distance") is not None else r for r in recs]
        try:
            out.append(_activity(file_id, s, recs, lens, leg_laps))
        except EmptyActivity:
            continue
    if not out:
        raise EmptyActivity("No activity data in this file (started and stopped right away).")
    return out


def _activity(file_id: dict, session: dict, records: list[dict], lengths: list[dict],
              laps: list[dict]) -> ParsedFit:
    if not session and not records:
        raise FitParseError("FIT file has no activity data.")
    timer = session.get("total_timer_time")
    if timer is None and records:
        timer = (_aware(records[-1]["timestamp"]) - _aware(records[0]["timestamp"])).total_seconds()
    if (timer or 0) < MIN_ACTIVITY_S:
        raise EmptyActivity("No activity data in this file (started and stopped right away).")

    first_ts = _aware(records[0]["timestamp"]) if records else None
    start_at = _aware(session["start_time"]) if "start_time" in session else first_ts
    if start_at is None:
        raise FitParseError("FIT file has no start time.")
    if "total_elapsed_time" in session:
        duration_s = int(round(session["total_elapsed_time"]))
    elif records:
        duration_s = int((_aware(records[-1]["timestamp"]) - start_at).total_seconds())
    else:
        raise FitParseError("FIT file has no duration.")

    streams = Streams()
    for r in records:
        streams.t_offset.append(int((_aware(r["timestamp"]) - start_at).total_seconds()))
        streams.power.append(_int(r.get("power")))
        streams.hr.append(_hr(r.get("heart_rate")))
        streams.cadence.append(_int(r.get("cadence")))
        streams.speed.append(r.get("enhanced_speed", r.get("speed")))
        streams.altitude.append(r.get("enhanced_altitude", r.get("altitude")))
        streams.distance.append(r.get("distance"))

    fit_sport = str(session.get("sport", "generic"))
    fit_sub = session.get("sub_sport")
    active = [ln for ln in lengths if ln.get("length_type") == "active"]
    distances = [d for d in streams.distance if d is not None]

    return ParsedFit(
        sport=SPORTS.get(fit_sport, "other"),
        sub_type=f"{fit_sport}/{fit_sub}" if fit_sub is not None else fit_sport,
        manufacturer=str(file_id["manufacturer"]) if "manufacturer" in file_id else None,
        start_at=start_at,
        end_at=start_at + timedelta(seconds=duration_s),
        duration_s=duration_s,
        moving_s=_int(session.get("total_timer_time")),
        distance_m=session.get("total_distance", distances[-1] if distances else None),
        elevation_m=session.get("total_ascent"),
        avg_hr=_hr(session.get("avg_heart_rate")) or _avg(streams.hr),
        max_hr=_hr(session.get("max_heart_rate")) or _max(streams.hr),
        avg_power=_int(session.get("avg_power")) or _avg(streams.power),
        max_power=_int(session.get("max_power")) or _max(streams.power),
        avg_cadence=_int(session.get("avg_cadence")) or _avg(streams.cadence),
        calories=_int(session.get("total_calories")),
        pool_length_m=session.get("pool_length"),
        swim_lengths=len(active) if active else _int(session.get("num_active_lengths")),
        swim_strokes=sum(ln.get("total_strokes", 0) for ln in active) if active else _int(session.get("total_strokes")),
        streams=streams,
        swim_active_s=_int(sum(ln.get("total_timer_time", ln.get("total_elapsed_time", 0)) for ln in active))
        if active else None,
        laps=[_lap(lap, start_at) for lap in laps],
    )
