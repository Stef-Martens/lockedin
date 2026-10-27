-- Zwift's FTP next to the owner's own entries: read back from the app's workouts ridden in ERG mode, or from a
-- reading in Zwift's logs. One row per day per source; activity_id is the ride a Zwift value was read from.
alter table ftp_history add column if not exists source text not null default 'owner' check (source in ('owner', 'zwift'));
alter table ftp_history add column if not exists activity_id bigint references activities(id) on delete set null;
alter table ftp_history drop constraint if exists ftp_history_pkey;
alter table ftp_history add primary key (effective_from, source);
