-- How often the owner wants a body check-in reminder, and whether it also nudges the Hevy upload.
alter table profile
  add column reminder_weeks smallint not null default 2 check (reminder_weeks in (1, 2, 4)),
  add column reminder_hevy boolean not null default true;
