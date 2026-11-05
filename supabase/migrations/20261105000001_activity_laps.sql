-- The laps a watch records (for a planned workout, one per step). Null = the file wasn't read for laps yet,
-- [] = it has none. coach_ro already selects the whole activities table, so it sees this column too.
alter table activities add column if not exists laps jsonb;
