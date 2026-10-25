-- AI coach: goals, stored conversations, and a locked-down way for the coach to query training data.

create table goals (
  id bigint generated always as identity primary key,
  text text not null check (length(trim(text)) > 0),
  area text, target text,
  status text not null default 'active' check (status in ('active', 'achieved', 'dropped')),
  source text not null default 'coach' check (source in ('coach', 'manual')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now());

create table coach_conversations (
  id bigint generated always as identity primary key,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now());

-- Append-only: content is exactly what was sent to the model, so a conversation replays unchanged.
create table coach_messages (
  id bigint generated always as identity primary key,
  conversation_id bigint not null references coach_conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content jsonb not null,
  created_at timestamptz not null default now());
create index coach_messages_conversation_idx on coach_messages (conversation_id, id);

alter table profile add column last_goal_review_at timestamptz;

alter table goals enable row level security;
alter table coach_conversations enable row level security;
alter table coach_messages enable row level security;
revoke all on goals, coach_conversations, coach_messages from anon, authenticated;

-- coach_ro can only SELECT the training tables below. Raw uploads, import logs, streams and the coach's
-- own transcripts stay out of reach.
do $$ begin
  if not exists (select from pg_roles where rolname = 'coach_ro') then create role coach_ro nologin; end if;
end $$;
grant coach_ro to current_user;
grant usage on schema public to coach_ro;

do $$ declare t text; begin
  foreach t in array array['activities', 'gym_workouts', 'gym_sets', 'exercises', 'measurements',
                           'measurement_types', 'muscles', 'library_exercises', 'library_muscles', 'profile', 'goals'] loop
    execute format('grant select on public.%I to coach_ro', t);
    execute format('drop policy if exists coach_read on public.%I', t);
    execute format('create policy coach_read on public.%I for select to coach_ro using (true)', t);
  end loop; end $$;

-- The coach's queries run inside this function. Because it is SECURITY DEFINER and owned by coach_ro,
-- Postgres refuses any attempt to switch role from inside it (set_config('role', ...) included).
-- The caller wraps it in a read-only transaction with a statement timeout. It lives outside the
-- API-exposed public schema and only the app's own role may call it.
create schema if not exists coach;
revoke all on schema coach from public;
grant usage, create on schema coach to coach_ro;

create or replace function coach.run_query(sql text, max_rows integer) returns json
language plpgsql security definer set search_path = public as $$
declare result json;
begin
  -- Newlines keep a trailing "--" comment in the query from swallowing the wrapper.
  execute format(E'select coalesce(json_agg(r), ''[]''::json) from (select * from (\n%s\n) q limit %s) r',
                 sql, max_rows) into result;
  return result;
end $$;

alter function coach.run_query(text, integer) owner to coach_ro;
revoke create on schema coach from coach_ro;
revoke all on function coach.run_query(text, integer) from public, anon, authenticated;
grant execute on function coach.run_query(text, integer) to current_user;
