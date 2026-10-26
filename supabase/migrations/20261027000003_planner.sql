-- Workout planner: training preferences, goals tied to a lift, and saved plans.

alter table profile
  add column avoid_muscles text[] not null default '{}',
  add column never_exercises text[] not null default '{}',
  add column coach_notes text not null default '' check (length(coach_notes) <= 1000);

-- The lift a goal is about (exact exercise name), when it is about one.
alter table goals add column exercise text;

-- One row per built plan; the newest per day is current while its freshness key still matches.
create table workout_plans (
  id bigint generated always as identity primary key,
  day text,                                  -- Hevy workout title; null = "just what I've missed"
  built_on date not null,                    -- local (Brussels) date it was built for
  source_activity_id bigint,                 -- the routine's latest workout when built
  prefs_hash text not null,
  items jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now());
create index workout_plans_day_idx on workout_plans (day, id desc);

alter table workout_plans enable row level security;
revoke all on workout_plans from anon, authenticated;
