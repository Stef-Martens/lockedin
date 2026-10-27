-- Time off: a vacation or an injury from a start day, with per-activity restrictions that each end on their own day.
-- restrictions is [{"category": "run", "until": "2026-12-17"}, ...]; categories: run, bike, swim, upper, core, lower, all.
create table if not exists time_off (
  id bigint generated always as identity primary key,
  reason text not null check (reason in ('vacation', 'injury')),
  label text,
  start_day date not null,
  restrictions jsonb not null,
  created_at timestamptz not null default now());
create index if not exists time_off_start_day on time_off (start_day);

alter table time_off enable row level security;
revoke all on time_off from anon, authenticated;
grant select on time_off to coach_ro;
drop policy if exists coach_read on time_off;
create policy coach_read on time_off for select to coach_ro using (true);
