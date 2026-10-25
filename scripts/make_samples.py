"""Write small synthetic FIT files to samples/ so imports can be tested without real data.

Run with `make samples`. The files are committed; re-running reproduces them exactly.
"""

from datetime import UTC, datetime
from pathlib import Path

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.length_message import LengthMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import (
    Event, EventType, FileType, LengthType, Manufacturer, Sport, SubSport, SwimStroke,
)

OUT = Path(__file__).resolve().parent.parent / "samples"


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def build(path: str, *, manufacturer: int, sport: Sport, sub_sport: SubSport, start: datetime,
          duration_s: int, records: list[dict], session: dict, lengths: list[dict] | None = None) -> None:
    b = FitFileBuilder(auto_define=True, min_string_size=50)
    t0 = ms(start)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = manufacturer
    fid.product = 0
    fid.serial_number = 0x1234
    fid.time_created = t0
    b.add(fid)

    ev = EventMessage()
    ev.event, ev.event_type, ev.timestamp = Event.TIMER, EventType.START, t0
    b.add(ev)

    for r in records:
        m = RecordMessage()
        m.timestamp = t0 + r.pop("t") * 1000
        for k, v in r.items():
            if v is not None:
                setattr(m, k, v)
        b.add(m)

    for ln in lengths or []:
        m = LengthMessage()
        m.start_time = t0 + ln["t"] * 1000
        m.timestamp = t0 + (ln["t"] + ln["dur"]) * 1000
        m.total_elapsed_time = m.total_timer_time = ln["dur"]
        m.length_type = LengthType.ACTIVE
        m.total_strokes = ln["strokes"]
        m.swim_stroke = SwimStroke.FREESTYLE
        b.add(m)

    t_end = t0 + duration_s * 1000
    ev = EventMessage()
    ev.event, ev.event_type, ev.timestamp = Event.TIMER, EventType.STOP_ALL, t_end
    b.add(ev)

    lap = LapMessage()
    lap.start_time, lap.timestamp = t0, t_end
    lap.total_elapsed_time = lap.total_timer_time = duration_s
    b.add(lap)

    s = SessionMessage()
    s.start_time, s.timestamp = t0, t_end
    s.sport, s.sub_sport = sport, sub_sport
    s.total_elapsed_time = s.total_timer_time = duration_s
    for k, v in session.items():
        setattr(s, k, v)
    b.add(s)

    act = ActivityMessage()
    act.timestamp, act.total_timer_time, act.num_sessions = t_end, duration_s, 1
    b.add(act)

    b.build().to_file(str(OUT / path))


def ride(with_hr: bool) -> tuple[list[dict], dict]:
    speed = 30000 / 3600
    recs = [
        {
            "t": t,
            "power": 150 if t < 1800 else 250,
            "heart_rate": round(130 + 30 * t / 3599) if with_hr else None,
            "cadence": 85,
            "speed": speed,
            "distance": speed * t,
            "altitude": 10.0 + (t % 600) / 10,
        }
        for t in range(3600)
    ]
    sess = {"total_distance": 30000.0, "avg_power": 200, "max_power": 250, "avg_cadence": 85,
            "total_ascent": 120, "total_calories": 720}
    if with_hr:
        sess |= {"avg_heart_rate": 145, "max_heart_rate": 160}
    return recs, sess


def hr_every(seconds: int, duration_s: int, lo: int, hi: int, **extra) -> list[dict]:
    return [{"t": t, "heart_rate": round(lo + (hi - lo) * t / duration_s), **extra}
            for t in range(0, duration_s + 1, seconds)]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    zwift = Manufacturer.ZWIFT.value
    watch = Manufacturer.DEVELOPMENT.value

    recs, sess = ride(with_hr=True)
    build("zwift_ride.fit", manufacturer=zwift, sport=Sport.CYCLING, sub_sport=SubSport.VIRTUAL_ACTIVITY,
          start=datetime(2026, 10, 20, 17, 0, tzinfo=UTC), duration_s=3600, records=recs, session=sess)
    recs, sess = ride(with_hr=False)
    build("zwift_ride_no_hr.fit", manufacturer=zwift, sport=Sport.CYCLING, sub_sport=SubSport.VIRTUAL_ACTIVITY,
          start=datetime(2026, 10, 20, 17, 0, tzinfo=UTC), duration_s=3600, records=recs, session=sess)

    build("watch_indoor_cycle.fit", manufacturer=watch, sport=Sport.CYCLING, sub_sport=SubSport.INDOOR_CYCLING,
          start=datetime(2026, 10, 20, 16, 58, tzinfo=UTC), duration_s=3700,
          records=hr_every(5, 3700, 128, 162),
          session={"avg_heart_rate": 145, "max_heart_rate": 162, "total_calories": 650})

    run_speed = 8000 / 2700
    build("watch_run.fit", manufacturer=watch, sport=Sport.RUNNING, sub_sport=SubSport.GENERIC,
          start=datetime(2026, 10, 22, 7, 0, tzinfo=UTC), duration_s=2700,
          records=[{"t": t, "heart_rate": round(140 + 20 * t / 2700), "speed": run_speed,
                    "distance": run_speed * t, "cadence": 82} for t in range(2701)],
          session={"total_distance": 8000.0, "avg_heart_rate": 150, "max_heart_rate": 165,
                   "total_calories": 560, "total_ascent": 35})

    lengths = [{"t": i * 45, "dur": 45, "strokes": 18} for i in range(40)]
    build("watch_pool_swim.fit", manufacturer=watch, sport=Sport.SWIMMING, sub_sport=SubSport.LAP_SWIMMING,
          start=datetime(2026, 10, 23, 18, 0, tzinfo=UTC), duration_s=1800,
          records=[{"t": (i + 1) * 45, "heart_rate": 135, "distance": 25.0 * (i + 1)} for i in range(40)],
          lengths=lengths,
          session={"total_distance": 1000.0, "pool_length": 25.0, "num_active_lengths": 40,
                   "num_lengths": 40, "total_strokes": 720, "avg_heart_rate": 135, "max_heart_rate": 150,
                   "total_calories": 300})

    build("watch_strength.fit", manufacturer=watch, sport=Sport.TRAINING, sub_sport=SubSport.STRENGTH_TRAINING,
          start=datetime(2026, 10, 24, 17, 5, tzinfo=UTC), duration_s=3000,
          records=hr_every(5, 3000, 95, 130),
          session={"avg_heart_rate": 112, "max_heart_rate": 140, "total_calories": 280})

    build("watch_walk.fit", manufacturer=watch, sport=Sport.WALKING, sub_sport=SubSport.GENERIC,
          start=datetime(2026, 10, 24, 12, 0, tzinfo=UTC), duration_s=1200,
          records=hr_every(5, 1200, 90, 100, ),
          session={"total_distance": 1500.0, "avg_heart_rate": 95, "max_heart_rate": 102, "total_calories": 90})

    (OUT / "corrupt.fit").write_bytes((OUT / "zwift_ride.fit").read_bytes()[:200])
    print(f"wrote samples to {OUT}")


if __name__ == "__main__":
    main()
