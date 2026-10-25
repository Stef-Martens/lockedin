from sqlalchemy import text

OWNER = ["Overhead Press (Dumbbell)", "Lateral Raise (Dumbbell)", "Incline Bench Press (Dumbbell)", "Hammer Curl (Cable)",
         "Bicep Curl (Cable)", "Preacher Curl (Machine)", "Bench Press (Barbell)", "Seated Cable Row - V Grip (Cable)",
         "Pull Up", "Triceps Extension (Cable)", "Chest Supported Reverse Fly (Dumbbell)", "Chest Fly (Machine)",
         "Leg Press Horizontal (Machine)", "Leg Extension (Machine)", "Seated Leg Curl (Machine)", "Cable Crunch",
         "Cable Twist (Up to down)", "Triceps Dip", "Lat Pulldown (Cable)", "Lateral Raise (Cable)", "Triceps Pushdown",
         "Chest Supported Incline Row (Dumbbell)", "Side Bend (Cable)"]


def test_every_owner_exercise_has_a_primary_muscle(conn):
    mapped = set(conn.execute(text("select exercise_name from library_muscles where role = 'primary'")).scalars())
    assert [e for e in OWNER if e not in mapped] == []


def test_every_flaggable_muscle_has_a_primary_exercise(conn):
    rows = conn.execute(text(
        "select m.key from muscles m where m.target_low > 0 and not exists "
        "(select 1 from library_muscles l where l.muscle_key = m.key and l.role = 'primary')"
    )).scalars().all()
    assert rows == []


def test_twenty_muscles_with_targets(conn):
    m = {r.key: r for r in conn.execute(text("select * from muscles"))}
    assert len(m) == 20
    # target_low = minimum effective dose (so "low" means neglected), target_high = upper growth range
    assert (m["side_delt"].target_low, m["side_delt"].target_high) == (4, 16)
    assert (m["calves"].target_low, m["traps" if "traps" in m else "upper_back_traps"].target_low) == (3, 2)
    assert m["forearms"].target_low == 0 and m["abductors"].target_low == 0
    assert m["calves"].region == "legs"


def test_related_ratios(conn):
    row = conn.execute(text("select related_to, ratio, equipment from library_exercises where name = 'Shrug (Dumbbell)'")).one()
    assert tuple(row) == ("Overhead Press (Dumbbell)", 1.2, "dumbbell")
    assert conn.execute(text("select equipment from library_exercises where name = 'Pull Up'")).scalar() == "bodyweight"


def test_seated_row_has_two_primaries(conn):
    rows = conn.execute(text("select muscle_key from library_muscles where exercise_name = 'Seated Cable Row - V Grip (Cable)' "
                             "and role = 'primary' order by muscle_key")).scalars().all()
    assert rows == ["lats", "mid_back"]
