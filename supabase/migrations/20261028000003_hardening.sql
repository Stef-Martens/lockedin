-- Hardening: an index the gym queries and cascade deletes need, and the coach's token usage for its daily budget.

-- gym_sets is read per workout (activities summary, session detail) and deleted by cascade from gym_workouts.
create index if not exists gym_sets_workout_idx on gym_sets (workout_id, exercise_order, set_index);

-- One row per model call (per attempt when a refusal falls back to another model). Lives in the private coach
-- schema: not exposed through the Supabase API, and coach_ro (the coach's SQL tool) gets no access to it.
create table coach.usage (
  id bigint generated always as identity primary key,
  conversation_id bigint references public.coach_conversations(id) on delete set null,
  model text not null,
  input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cache_read_tokens integer not null default 0,
  cache_write_tokens integer not null default 0,
  cost_usd numeric(12, 6) not null,  -- estimated at the prices when it was recorded
  created_at timestamptz not null default now());
create index coach_usage_created_idx on coach.usage (created_at);
revoke all on coach.usage from public, anon, authenticated, coach_ro;
