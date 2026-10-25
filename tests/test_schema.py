from sqlalchemy import text

TABLES = {
    "profile", "activities", "activity_streams", "fit_files", "exercises",
    "gym_workouts", "gym_sets", "measurement_types", "measurements", "import_log",
}


def test_all_tables_exist_with_rls(conn):
    rows = conn.execute(text(
        "select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and relkind = 'r'"
    )).all()
    assert {r[0] for r in rows} == TABLES
    assert all(r[1] for r in rows)


def test_anon_and_authenticated_have_no_privileges(conn):
    rows = conn.execute(text(
        "select grantee, table_name from information_schema.role_table_grants "
        "where table_schema = 'public' and grantee in ('anon', 'authenticated')"
    )).all()
    assert rows == []


def test_seeds(conn):
    assert conn.execute(text("select count(*) from profile")).scalar() == 1
    names = conn.execute(text("select name from measurement_types order by id")).scalars().all()
    assert names == ["Weight", "Chest", "Left arm", "Right arm", "Waist", "Hips", "Left thigh", "Right thigh", "Shoulders"]
