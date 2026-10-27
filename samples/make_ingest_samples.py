"""Synthetic FIT files for the ingest edge cases: a Zwift run, a brick (multisport) file, swims with rest
and in open water, and a second Watch file during a ride. Companion to scripts/make_samples.py.

Run with `.venv/bin/python samples/make_ingest_samples.py`; re-running reproduces the files exactly.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fit_tool.fit_file_builder import FitFileBuilder  # noqa: E402
from fit_tool.profile.messages.activity_message import ActivityMessage  # noqa: E402
from fit_tool.profile.messages.event_message import EventMessage  # noqa: E402
from fit_tool.profile.messages.file_id_message import FileIdMessage  # noqa: E402
from fit_tool.profile.messages.lap_message import LapMessage  # noqa: E402
from fit_tool.profile.messages.length_message import LengthMessage  # noqa: E402
from fit_tool.profile.messages.record_message import RecordMessage  # noqa: E402
from fit_tool.profile.messages.session_message import SessionMessage  # noqa: E402
from fit_tool.profile.profile_type import (  # noqa: E402
    Event, EventType, FileType, LengthType, Manufacturer, Sport, SubSport, SwimStroke,
)
from make_samples import OUT, build, hr_every, ms  # noqa: E402


def multisport(path: str, *, manufacturer: int, start: datetime, legs: list[dict]) -> None:
    """One file, one session per leg (sport, sub_sport, duration_s, records, session), back to back."""
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    t0 = ms(start)
    fid = FileIdMessage()
    fid.type, fid.manufacturer, fid.product, fid.serial_number, fid.time_created = (
        FileType.ACTIVITY, manufacturer, 0, 0x4242, t0)
    b.add(fid)
    ev = EventMessage()
    ev.event, ev.event_type, ev.timestamp = Event.TIMER, EventType.START, t0
    b.add(ev)
    t, sessions = t0, []
    for leg in legs:
        for r in leg["records"]:
            m = RecordMessage()
            m.timestamp = t + r.pop("t") * 1000
            for k, v in r.items():
                setattr(m, k, v)
            b.add(m)
        end = t + leg["duration_s"] * 1000
        lap = LapMessage()
        lap.start_time, lap.timestamp = t, end
        lap.total_elapsed_time = lap.total_timer_time = leg["duration_s"]
        b.add(lap)
        s = SessionMessage()
        s.start_time, s.timestamp = t, end
        s.sport, s.sub_sport = leg["sport"], leg["sub_sport"]
        s.total_elapsed_time = s.total_timer_time = leg["duration_s"]
        for k, v in leg.get("session", {}).items():
            setattr(s, k, v)
        sessions.append(s)
        t = end
    ev = EventMessage()
    ev.event, ev.event_type, ev.timestamp = Event.TIMER, EventType.STOP_ALL, t
    b.add(ev)
    for s in sessions:
        b.add(s)
    act = ActivityMessage()
    act.timestamp, act.total_timer_time, act.num_sessions = t, (t - t0) // 1000, len(legs)
    b.add(act)
    b.build().to_file(str(OUT / path))


def pool_swim_with_rest(path: str, start: datetime) -> None:
    """20 × 25 m, 2 min rest at the wall, 20 × 25 m: 30 min swimming in 32 min."""
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    t0 = ms(start)
    fid = FileIdMessage()
    fid.type, fid.manufacturer, fid.product, fid.serial_number, fid.time_created = (
        FileType.ACTIVITY, Manufacturer.DEVELOPMENT.value, 0, 0x1234, t0)
    b.add(fid)
    ev = EventMessage()
    ev.event, ev.event_type, ev.timestamp = Event.TIMER, EventType.START, t0
    b.add(ev)
    lengths = [(i * 45, 45, LengthType.ACTIVE) for i in range(20)] + [(900, 120, LengthType.IDLE)]
    lengths += [(1020 + i * 45, 45, LengthType.ACTIVE) for i in range(20)]
    done = 0
    for t, dur, kind in lengths:
        m = LengthMessage()
        m.start_time, m.timestamp = t0 + t * 1000, t0 + (t + dur) * 1000
        m.total_elapsed_time = m.total_timer_time = dur
        m.length_type = kind
        if kind == LengthType.ACTIVE:
            m.total_strokes, m.swim_stroke = 18, SwimStroke.FREESTYLE
            done += 1
            r = RecordMessage()
            r.timestamp, r.heart_rate, r.distance = t0 + (t + dur) * 1000, 135, 25.0 * done
            b.add(r)
        b.add(m)
    duration = 1920
    ev = EventMessage()
    ev.event, ev.event_type, ev.timestamp = Event.TIMER, EventType.STOP_ALL, t0 + duration * 1000
    b.add(ev)
    lap = LapMessage()
    lap.start_time, lap.timestamp = t0, t0 + duration * 1000
    lap.total_elapsed_time = lap.total_timer_time = duration
    b.add(lap)
    s = SessionMessage()
    s.start_time, s.timestamp = t0, t0 + duration * 1000
    s.sport, s.sub_sport = Sport.SWIMMING, SubSport.LAP_SWIMMING
    s.total_elapsed_time = s.total_timer_time = duration
    s.total_distance, s.pool_length, s.num_active_lengths, s.num_lengths = 1000.0, 25.0, 40, 41
    s.total_strokes, s.avg_heart_rate, s.max_heart_rate = 720, 135, 150
    b.add(s)
    act = ActivityMessage()
    act.timestamp, act.total_timer_time, act.num_sessions = t0 + duration * 1000, duration, 1
    b.add(act)
    b.build().to_file(str(OUT / path))


def main() -> None:
    zwift, watch = Manufacturer.ZWIFT.value, Manufacturer.DEVELOPMENT.value

    speed = 10000 / 2400  # 10 km in 40 min
    build("zwift_run.fit", manufacturer=zwift, sport=Sport.RUNNING, sub_sport=SubSport.VIRTUAL_ACTIVITY,
          start=datetime(2026, 10, 21, 18, 0, tzinfo=UTC), duration_s=2400,
          records=[{"t": t, "heart_rate": 150, "speed": speed, "distance": speed * t, "cadence": 85}
                   for t in range(2400)],
          session={"total_distance": 10000.0, "avg_heart_rate": 150, "max_heart_rate": 165})
    build("watch_indoor_run.fit", manufacturer=watch, sport=Sport.RUNNING, sub_sport=SubSport.TREADMILL,
          start=datetime(2026, 10, 21, 17, 59, tzinfo=UTC), duration_s=2520,
          records=hr_every(5, 2520, 130, 168),
          session={"total_distance": 9800.0, "avg_heart_rate": 151, "max_heart_rate": 168})

    # The Watch's indoor cycle was stopped and a second one started for the last 20 min of zwift_ride_no_hr
    build("watch_indoor_cycle_tail.fit", manufacturer=watch, sport=Sport.CYCLING, sub_sport=SubSport.INDOOR_CYCLING,
          start=datetime(2026, 10, 20, 17, 40, tzinfo=UTC), duration_s=1200,
          records=hr_every(5, 1200, 100, 100),
          session={"avg_heart_rate": 100, "max_heart_rate": 100})

    ride_speed = 30000 / 3600
    run_speed = 5000 / 1500
    multisport("watch_brick.fit", manufacturer=watch, start=datetime(2026, 10, 25, 8, 0, tzinfo=UTC), legs=[
        {"sport": Sport.CYCLING, "sub_sport": SubSport.ROAD, "duration_s": 3600,
         "records": [{"t": t, "heart_rate": 140, "power": 200, "speed": ride_speed, "distance": ride_speed * t}
                     for t in range(3600)],
         "session": {"total_distance": 30000.0, "avg_heart_rate": 140, "max_heart_rate": 150, "avg_power": 200}},
        {"sport": Sport.TRANSITION, "sub_sport": SubSport.GENERIC, "duration_s": 30,
         "records": [{"t": t, "heart_rate": 145} for t in range(0, 30, 5)], "session": {}},
        {"sport": Sport.RUNNING, "sub_sport": SubSport.STREET, "duration_s": 1500,
         "records": [{"t": t, "heart_rate": 160, "speed": run_speed, "distance": run_speed * t}
                     for t in range(1500)],
         "session": {"total_distance": 5000.0, "avg_heart_rate": 160, "max_heart_rate": 172}},
    ])

    pool_swim_with_rest("watch_pool_swim_rest.fit", datetime(2026, 10, 26, 18, 0, tzinfo=UTC))
    ow_speed = 1500 / 1800
    build("watch_open_water.fit", manufacturer=watch, sport=Sport.SWIMMING, sub_sport=SubSport.OPEN_WATER,
          start=datetime(2026, 8, 15, 9, 0, tzinfo=UTC), duration_s=1800,
          records=[{"t": t, "heart_rate": 140, "distance": ow_speed * t} for t in range(0, 1801, 10)],
          session={"total_distance": 1500.0, "avg_heart_rate": 140, "max_heart_rate": 152})
    print(f"wrote ingest samples to {OUT}")


if __name__ == "__main__":
    main()
