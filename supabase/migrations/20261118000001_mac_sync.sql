-- What the Mac sync last did, and the latest "Check again" from the site. One row: the Mac reports every full
-- run, polls once a minute for an open request, and answers it with a run that names the request it answers.
create table if not exists mac_sync (
  id int primary key default 1 check (id = 1),
  last_run_at timestamptz,
  last_seen_at timestamptz,
  last_run_uploaded int,
  last_run_errors int,
  check_requested_at timestamptz,
  check_done_at timestamptz,
  check_uploaded int
);
insert into mac_sync (id) values (1) on conflict do nothing;
alter table mac_sync enable row level security;
revoke all on mac_sync from anon, authenticated;
