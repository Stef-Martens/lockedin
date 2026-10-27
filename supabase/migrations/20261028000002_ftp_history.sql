-- The owner's FTP over time, so a new FTP scores rides from that day on and leaves older ones alone.
-- A row without an FTP means "estimated from rides from this day on" (the owner cleared it).
-- profile.ftp_override stays as the current value for older readers.
create table if not exists ftp_history (
  effective_from date primary key,
  ftp smallint check (ftp between 50 and 600),
  created_at timestamptz not null default now());

-- Until now the one override scored every ride, so it takes effect from the first activity (Brussels day):
-- no existing ride is rescored by this migration. Rides backfilled from before that get the estimate of their era.
insert into ftp_history (effective_from, ftp)
select coalesce((select min((start_at at time zone 'Europe/Brussels')::date) from activities),
                (now() at time zone 'Europe/Brussels')::date), ftp_override
from profile where id = 1 and ftp_override is not null
on conflict do nothing;

alter table ftp_history enable row level security;
revoke all on ftp_history from anon, authenticated;
grant select on ftp_history to coach_ro;
drop policy if exists coach_read on ftp_history;
create policy coach_read on ftp_history for select to coach_ro using (true);
