-- e1RM is only estimated from 1–20 rep sets and never for assisted lifts (as lockedin/hevy/importer.py e1rm()).
update gym_sets s set e1rm = null from exercises e
where e.id = s.exercise_id and s.e1rm is not null and (s.reps > 20 or e.name ilike '%assisted%');

-- A FIT file the parser can't read: re-uploads of the same bytes get the stored answer instead of a re-parse.
alter table fit_files add column unreadable boolean not null default false;
