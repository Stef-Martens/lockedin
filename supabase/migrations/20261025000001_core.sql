-- LockedIn core schema. All timestamps UTC; distances in metres unless the column says otherwise.

create table profile (
  id smallint primary key default 1 check (id = 1),
  date_of_birth date, height_cm real, sex text check (sex in ('male','female')),
  max_hr_override smallint, ftp_override smallint, resting_hr_override smallint,
  updated_at timestamptz not null default now());
insert into profile (id) values (1);

create table activities (
  id bigint generated always as identity primary key,
  source text not null check (source in ('zwift','healthfit','hevy')),
  source_ref text not null,
  sport text not null check (sport in ('bike','run','swim','gym','other')),
  sub_type text,
  start_at timestamptz not null, end_at timestamptz not null,
  duration_s integer not null, moving_s integer,
  distance_m real, elevation_m real,
  avg_hr smallint, max_hr smallint, calories integer,
  avg_power smallint, max_power smallint, avg_cadence smallint,
  np real, if_ real, tss real, best_20m_power real,
  avg_pace_s_per_km real, swim_pace_s_per_100m real,
  swim_lengths integer, swim_strokes integer, pool_length_m real,
  effort_class text,
  hr_merged_from bigint references activities(id) on delete set null,
  superseded_by bigint references activities(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (source, source_ref));
create index activities_start_idx on activities (start_at desc);
create index activities_sport_start_idx on activities (sport, start_at desc);

-- One row per activity; arrays are aligned by index with t_offset (seconds from start).
create table activity_streams (
  activity_id bigint primary key references activities(id) on delete cascade,
  t_offset integer[] not null, power smallint[], hr smallint[], cadence smallint[],
  speed real[], altitude real[], distance real[]);

create table fit_files (
  sha256 text primary key, filename text not null, source text,
  uploaded_at timestamptz not null default now(),
  activity_id bigint references activities(id) on delete set null,
  parse_status text not null check (parse_status in ('ok','error')), error text);

create table exercises (
  id bigint generated always as identity primary key,
  name text not null unique, is_bodyweight boolean not null default false);

create table gym_workouts (
  activity_id bigint primary key references activities(id) on delete cascade,
  hevy_key text not null unique, title text not null, description text,
  content_hash text not null);

create table gym_sets (
  id bigint generated always as identity primary key,
  workout_id bigint not null references gym_workouts(activity_id) on delete cascade,
  exercise_id bigint not null references exercises(id),
  exercise_order smallint not null, set_index smallint not null,
  set_type text not null default 'normal',
  weight_kg real, reps smallint, distance_km real, duration_s integer, rpe real,
  superset_id text, notes text, e1rm real);
create index gym_sets_exercise_idx on gym_sets (exercise_id);

create table measurement_types (
  id bigint generated always as identity primary key,
  name text not null unique, unit text not null,
  kind text not null check (kind in ('weight','tape','other')));
insert into measurement_types (name, unit, kind) values
  ('Weight','kg','weight'),('Chest','cm','tape'),('Left arm','cm','tape'),('Right arm','cm','tape'),
  ('Waist','cm','tape'),('Hips','cm','tape'),('Left thigh','cm','tape'),('Right thigh','cm','tape'),
  ('Shoulders','cm','tape');

create table measurements (
  id bigint generated always as identity primary key,
  type_id bigint not null references measurement_types(id) on delete cascade,
  measured_on date not null, value real not null check (value > 0),
  source text not null default 'manual', note text,
  created_at timestamptz not null default now());

create table import_log (
  id bigint generated always as identity primary key,
  source text not null, at timestamptz not null default now(), summary jsonb not null);

-- Nothing is reachable through Supabase's auto-generated REST API: RLS on, no policies, no grants.
-- The FastAPI backend connects as its own role and does all access control.
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
  end loop; end $$;
revoke all on all tables in schema public from anon, authenticated;
