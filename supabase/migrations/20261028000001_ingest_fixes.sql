-- e1RM is only estimated from 1–12 rep sets and never for assisted lifts (as lockedin/hevy/importer.py e1rm()).
update gym_sets s set e1rm = null from exercises e
where e.id = s.exercise_id and s.e1rm is not null and (s.reps > 12 or e.name ilike '%assisted%');
