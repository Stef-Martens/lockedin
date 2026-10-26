-- Agenda: what the owner plans to do on which day; Zwift workouts become .zwo files via the Mac sync.
create table agenda_items (
  id bigint generated always as identity primary key,
  day date not null,
  sport text not null check (sport in ('gym', 'bike', 'run', 'swim', 'rest', 'other')),
  title text not null check (length(trim(title)) between 1 and 80),
  note text check (length(note) <= 500),
  optional boolean not null default false,
  routine text,                 -- gym: the Hevy routine (workout title) to do
  zwift jsonb,                  -- bike: structured workout blocks, rendered to .zwo by the server
  zwift_synced_at timestamptz,  -- when the Mac sync last fetched the current file
  sort smallint not null default 0,
  source text not null default 'manual' check (source in ('coach', 'manual')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now());
create index agenda_items_day_idx on agenda_items (day, sort, id);

alter table agenda_items enable row level security;
revoke all on agenda_items from anon, authenticated;

-- The coach may read the agenda with its read-only SQL too.
grant select on agenda_items to coach_ro;
drop policy if exists coach_read on agenda_items;
create policy coach_read on agenda_items for select to coach_ro using (true);
