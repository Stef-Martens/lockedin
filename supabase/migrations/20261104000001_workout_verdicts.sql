-- The coach's saved verdict on a workout. claimed_at is the claim that makes sure only one model call is paid for.
-- Not readable by the coach's read-only role.
create table if not exists workout_verdicts (
  activity_id bigint primary key references activities (id) on delete cascade,
  item_id bigint references agenda_items (id) on delete set null,
  label text check (label in ('on_plan', 'close', 'off_plan', 'unplanned')),
  body text,
  model text,
  claimed_at timestamptz,
  written_at timestamptz,
  failed_at timestamptz);

alter table workout_verdicts enable row level security;
revoke all on workout_verdicts from anon, authenticated;
