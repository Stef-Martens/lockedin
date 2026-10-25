"""Everything the focus engine knows, in one JSON-ready dict (also the AI coach's data tool in Plan 3)."""

from datetime import datetime

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Connection

from lockedin.fitness import ftp_at
from lockedin.focus.consistency import comeback, week_streak
from lockedin.focus.coverage import muscle_coverage, unmapped_exercises
from lockedin.focus.mix import effort_mix, session_suggestions
from lockedin.focus.suggest import gym_suggestions
from lockedin.focus.wins import plateaus, recent_wins
from lockedin.focus.zones import hr_zone_bounds, max_hr_at, power_zone_bounds


def focus_facts(conn: Connection, now: datetime) -> dict:
    max_hr, ftp = max_hr_at(conn, now), ftp_at(conn, now)
    return jsonable_encoder({
        "generated_at": now,
        "zones": {"max_hr": max_hr, "ftp": round(ftp) if ftp else None,
                  "hr_zones": hr_zone_bounds(max_hr) if max_hr else None,
                  "power_zones": power_zone_bounds(ftp) if ftp else None},
        "coverage": muscle_coverage(conn, now),
        "unmapped": unmapped_exercises(conn, now),
        "gym_suggestions": gym_suggestions(conn, now),
        "session_suggestions": session_suggestions(conn, now),
        "mix": {"run": effort_mix(conn, now, "run"), "bike": effort_mix(conn, now, "bike")},
        "plateaus": plateaus(conn, now),
        "wins": recent_wins(conn, now),
        "streak": week_streak(conn, now),
        "comeback": comeback(conn, now),
    })
