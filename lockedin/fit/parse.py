"""Decode a FIT activity file (Zwift or HealthFit) into a summary plus per-second streams."""

import io
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import fitdecode

Sport = Literal["bike", "run", "swim", "other"]
SPORTS: dict[str, Sport] = {"cycling": "bike", "running": "run", "swimming": "swim"}


class FitParseError(Exception):
    pass


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


def _values(frame) -> dict:
    return {f.name: f.value for f in frame.fields if f.value is not None}


def _int(v) -> int | None:
    return None if v is None else int(round(v))


def _avg(xs: list) -> int | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs)) if xs else None


def _max(xs: list) -> int | None:
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def parse_fit(data: bytes) -> ParsedFit:
    try:
        return _parse(data)
    except FitParseError:
        raise
    except Exception as e:  # unexpected field values in real-world files
        raise FitParseError(f"Could not read FIT file: {e}") from e


def _parse(data: bytes) -> ParsedFit:
    file_id: dict = {}
    session: dict = {}
    records: list[dict] = []
    lengths: list[dict] = []
    try:
        with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.RAISE) as fit:
            for frame in fit:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                    continue
                if frame.name == "file_id":
                    file_id = _values(frame)
                elif frame.name == "session" and not session:
                    session = _values(frame)
                elif frame.name == "record":
                    v = _values(frame)
                    if "timestamp" in v:
                        records.append(v)
                elif frame.name == "length":
                    lengths.append(_values(frame))
    except Exception as e:  # fitdecode raises several types for truncated/garbage input
        raise FitParseError(f"Could not read FIT file: {e}") from e

    if not session and not records:
        raise FitParseError("FIT file has no activity data.")

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
        streams.hr.append(_int(r.get("heart_rate")))
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
        avg_hr=_int(session.get("avg_heart_rate")) or _avg(streams.hr),
        max_hr=_int(session.get("max_heart_rate")) or _max(streams.hr),
        avg_power=_int(session.get("avg_power")) or _avg(streams.power),
        max_power=_int(session.get("max_power")) or _max(streams.power),
        avg_cadence=_int(session.get("avg_cadence")) or _avg(streams.cadence),
        calories=_int(session.get("total_calories")),
        pool_length_m=session.get("pool_length"),
        swim_lengths=len(active) if active else _int(session.get("num_active_lengths")),
        swim_strokes=sum(ln.get("total_strokes", 0) for ln in active) if active else _int(session.get("total_strokes")),
        streams=streams,
    )
