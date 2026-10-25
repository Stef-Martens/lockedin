-- Muscle taxonomy and exercise library for the focus engine.
-- Exercises are keyed by name, exactly as Hevy writes them; owner-tagged rows have created_by = 'owner'.
-- Weekly set targets are starting points (common hypertrophy guidance); target_low = 0 is never flagged low.

create table muscles (
  key text primary key, name text not null, region text not null,
  target_low real not null, target_high real not null, sort smallint not null);

create table library_exercises (
  name text primary key,
  equipment text not null check (equipment in ('barbell','dumbbell','cable','machine','bodyweight','other')),
  related_to text references library_exercises(name) on delete set null,
  ratio real,
  created_by text not null default 'seed');

create table library_muscles (
  exercise_name text not null references library_exercises(name) on delete cascade,
  muscle_key text not null references muscles(key),
  role text not null check (role in ('primary','secondary')),
  primary key (exercise_name, muscle_key));
create index library_muscles_muscle_idx on library_muscles (muscle_key);

insert into muscles (key, name, region, target_low, target_high, sort) values
  ('upper_chest', 'Upper chest', 'chest', 4, 10, 0),
  ('mid_lower_chest', 'Mid/lower chest', 'chest', 6, 12, 1),
  ('front_delt', 'Front delts', 'shoulders', 4, 10, 2),
  ('side_delt', 'Side delts', 'shoulders', 8, 16, 3),
  ('rear_delt', 'Rear delts', 'shoulders', 6, 12, 4),
  ('triceps', 'Triceps', 'arms', 8, 14, 5),
  ('biceps', 'Biceps', 'arms', 8, 14, 6),
  ('forearms', 'Forearms', 'arms', 0, 8, 7),
  ('lats', 'Lats', 'back', 8, 14, 8),
  ('mid_back', 'Mid back', 'back', 8, 14, 9),
  ('upper_back_traps', 'Traps', 'back', 4, 10, 10),
  ('lower_back', 'Lower back', 'back', 3, 8, 11),
  ('abs', 'Abs', 'core', 6, 12, 12),
  ('obliques', 'Obliques', 'core', 3, 8, 13),
  ('glutes', 'Glutes', 'legs', 6, 12, 14),
  ('quads', 'Quads', 'legs', 8, 14, 15),
  ('hamstrings', 'Hamstrings', 'legs', 6, 12, 16),
  ('adductors', 'Adductors', 'legs', 3, 8, 17),
  ('abductors', 'Abductors', 'legs', 0, 6, 18),
  ('calves', 'Calves', 'legs', 6, 12, 19);

insert into library_exercises (name, equipment) values
  ('Overhead Press (Dumbbell)', 'dumbbell'),
  ('Lateral Raise (Dumbbell)', 'dumbbell'),
  ('Lateral Raise (Cable)', 'cable'),
  ('Incline Bench Press (Dumbbell)', 'dumbbell'),
  ('Bench Press (Barbell)', 'barbell'),
  ('Chest Fly (Machine)', 'machine'),
  ('Triceps Dip', 'bodyweight'),
  ('Triceps Extension (Cable)', 'cable'),
  ('Triceps Pushdown', 'cable'),
  ('Hammer Curl (Cable)', 'cable'),
  ('Bicep Curl (Cable)', 'cable'),
  ('Preacher Curl (Machine)', 'machine'),
  ('Pull Up', 'bodyweight'),
  ('Lat Pulldown (Cable)', 'cable'),
  ('Seated Cable Row - V Grip (Cable)', 'cable'),
  ('Chest Supported Incline Row (Dumbbell)', 'dumbbell'),
  ('Chest Supported Reverse Fly (Dumbbell)', 'dumbbell'),
  ('Leg Press Horizontal (Machine)', 'machine'),
  ('Leg Extension (Machine)', 'machine'),
  ('Seated Leg Curl (Machine)', 'machine'),
  ('Cable Crunch', 'cable'),
  ('Cable Twist (Up to down)', 'cable'),
  ('Side Bend (Cable)', 'cable'),
  ('Standing Calf Raise (Machine)', 'machine'),
  ('Seated Calf Raise', 'machine'),
  ('Hip Thrust (Barbell)', 'barbell'),
  ('Romanian Deadlift (Barbell)', 'barbell'),
  ('Bulgarian Split Squat', 'bodyweight'),
  ('Hip Adduction (Machine)', 'machine'),
  ('Hip Abduction (Machine)', 'machine'),
  ('Back Extension (Hyperextension)', 'bodyweight'),
  ('Shrug (Dumbbell)', 'dumbbell'),
  ('Face Pull', 'cable'),
  ('Rear Delt Reverse Fly (Machine)', 'machine'),
  ('Overhead Triceps Extension (Cable)', 'cable'),
  ('Skullcrusher (Barbell)', 'barbell'),
  ('Incline Curl (Dumbbell)', 'dumbbell'),
  ('Wrist Curl (Barbell)', 'barbell'),
  ('Hanging Leg Raise', 'bodyweight'),
  ('Low Cable Fly Crossover', 'cable'),
  ('Cable Fly Crossover', 'cable'),
  ('Front Raise (Dumbbell)', 'dumbbell');

update library_exercises set related_to = 'Leg Press Horizontal (Machine)', ratio = 0.5 where name = 'Standing Calf Raise (Machine)';
update library_exercises set related_to = 'Leg Press Horizontal (Machine)', ratio = 0.3 where name = 'Seated Calf Raise';
update library_exercises set related_to = 'Leg Press Horizontal (Machine)', ratio = 0.6 where name = 'Hip Thrust (Barbell)';
update library_exercises set related_to = 'Leg Press Horizontal (Machine)', ratio = 0.4 where name = 'Romanian Deadlift (Barbell)';
update library_exercises set related_to = 'Overhead Press (Dumbbell)', ratio = 1.2 where name = 'Shrug (Dumbbell)';
update library_exercises set related_to = 'Seated Cable Row - V Grip (Cable)', ratio = 0.35 where name = 'Face Pull';
update library_exercises set related_to = 'Chest Supported Reverse Fly (Dumbbell)', ratio = 2.0 where name = 'Rear Delt Reverse Fly (Machine)';
update library_exercises set related_to = 'Triceps Extension (Cable)', ratio = 0.9 where name = 'Overhead Triceps Extension (Cable)';
update library_exercises set related_to = 'Triceps Extension (Cable)', ratio = 0.8 where name = 'Skullcrusher (Barbell)';
update library_exercises set related_to = 'Chest Fly (Machine)', ratio = 0.5 where name = 'Low Cable Fly Crossover';
update library_exercises set related_to = 'Chest Fly (Machine)', ratio = 0.5 where name = 'Cable Fly Crossover';
update library_exercises set related_to = 'Lateral Raise (Dumbbell)', ratio = 1.0 where name = 'Front Raise (Dumbbell)';

insert into library_muscles (exercise_name, muscle_key, role) values
  ('Overhead Press (Dumbbell)', 'front_delt', 'primary'),
  ('Lateral Raise (Dumbbell)', 'side_delt', 'primary'),
  ('Lateral Raise (Cable)', 'side_delt', 'primary'),
  ('Incline Bench Press (Dumbbell)', 'upper_chest', 'primary'),
  ('Bench Press (Barbell)', 'mid_lower_chest', 'primary'),
  ('Chest Fly (Machine)', 'mid_lower_chest', 'primary'),
  ('Triceps Dip', 'triceps', 'primary'),
  ('Triceps Extension (Cable)', 'triceps', 'primary'),
  ('Triceps Pushdown', 'triceps', 'primary'),
  ('Hammer Curl (Cable)', 'biceps', 'primary'),
  ('Bicep Curl (Cable)', 'biceps', 'primary'),
  ('Preacher Curl (Machine)', 'biceps', 'primary'),
  ('Pull Up', 'lats', 'primary'),
  ('Lat Pulldown (Cable)', 'lats', 'primary'),
  ('Seated Cable Row - V Grip (Cable)', 'mid_back', 'primary'),
  ('Seated Cable Row - V Grip (Cable)', 'lats', 'primary'),
  ('Chest Supported Incline Row (Dumbbell)', 'mid_back', 'primary'),
  ('Chest Supported Reverse Fly (Dumbbell)', 'rear_delt', 'primary'),
  ('Leg Press Horizontal (Machine)', 'quads', 'primary'),
  ('Leg Press Horizontal (Machine)', 'glutes', 'primary'),
  ('Leg Extension (Machine)', 'quads', 'primary'),
  ('Seated Leg Curl (Machine)', 'hamstrings', 'primary'),
  ('Cable Crunch', 'abs', 'primary'),
  ('Cable Twist (Up to down)', 'obliques', 'primary'),
  ('Side Bend (Cable)', 'obliques', 'primary'),
  ('Standing Calf Raise (Machine)', 'calves', 'primary'),
  ('Seated Calf Raise', 'calves', 'primary'),
  ('Hip Thrust (Barbell)', 'glutes', 'primary'),
  ('Romanian Deadlift (Barbell)', 'hamstrings', 'primary'),
  ('Romanian Deadlift (Barbell)', 'glutes', 'primary'),
  ('Bulgarian Split Squat', 'quads', 'primary'),
  ('Bulgarian Split Squat', 'glutes', 'primary'),
  ('Hip Adduction (Machine)', 'adductors', 'primary'),
  ('Hip Abduction (Machine)', 'abductors', 'primary'),
  ('Back Extension (Hyperextension)', 'lower_back', 'primary'),
  ('Shrug (Dumbbell)', 'upper_back_traps', 'primary'),
  ('Face Pull', 'rear_delt', 'primary'),
  ('Rear Delt Reverse Fly (Machine)', 'rear_delt', 'primary'),
  ('Overhead Triceps Extension (Cable)', 'triceps', 'primary'),
  ('Skullcrusher (Barbell)', 'triceps', 'primary'),
  ('Incline Curl (Dumbbell)', 'biceps', 'primary'),
  ('Wrist Curl (Barbell)', 'forearms', 'primary'),
  ('Hanging Leg Raise', 'abs', 'primary'),
  ('Low Cable Fly Crossover', 'upper_chest', 'primary'),
  ('Cable Fly Crossover', 'mid_lower_chest', 'primary'),
  ('Front Raise (Dumbbell)', 'front_delt', 'primary'),
  ('Overhead Press (Dumbbell)', 'side_delt', 'secondary'),
  ('Overhead Press (Dumbbell)', 'triceps', 'secondary'),
  ('Overhead Press (Dumbbell)', 'upper_chest', 'secondary'),
  ('Incline Bench Press (Dumbbell)', 'front_delt', 'secondary'),
  ('Incline Bench Press (Dumbbell)', 'triceps', 'secondary'),
  ('Bench Press (Barbell)', 'upper_chest', 'secondary'),
  ('Bench Press (Barbell)', 'front_delt', 'secondary'),
  ('Bench Press (Barbell)', 'triceps', 'secondary'),
  ('Chest Fly (Machine)', 'upper_chest', 'secondary'),
  ('Chest Fly (Machine)', 'front_delt', 'secondary'),
  ('Triceps Dip', 'mid_lower_chest', 'secondary'),
  ('Triceps Dip', 'front_delt', 'secondary'),
  ('Hammer Curl (Cable)', 'forearms', 'secondary'),
  ('Bicep Curl (Cable)', 'forearms', 'secondary'),
  ('Pull Up', 'biceps', 'secondary'),
  ('Pull Up', 'mid_back', 'secondary'),
  ('Lat Pulldown (Cable)', 'biceps', 'secondary'),
  ('Lat Pulldown (Cable)', 'mid_back', 'secondary'),
  ('Seated Cable Row - V Grip (Cable)', 'biceps', 'secondary'),
  ('Seated Cable Row - V Grip (Cable)', 'rear_delt', 'secondary'),
  ('Chest Supported Incline Row (Dumbbell)', 'lats', 'secondary'),
  ('Chest Supported Incline Row (Dumbbell)', 'rear_delt', 'secondary'),
  ('Chest Supported Incline Row (Dumbbell)', 'biceps', 'secondary'),
  ('Chest Supported Reverse Fly (Dumbbell)', 'mid_back', 'secondary'),
  ('Leg Press Horizontal (Machine)', 'hamstrings', 'secondary'),
  ('Leg Press Horizontal (Machine)', 'adductors', 'secondary'),
  ('Cable Twist (Up to down)', 'abs', 'secondary'),
  ('Hip Thrust (Barbell)', 'hamstrings', 'secondary'),
  ('Romanian Deadlift (Barbell)', 'lower_back', 'secondary'),
  ('Bulgarian Split Squat', 'adductors', 'secondary'),
  ('Hip Abduction (Machine)', 'glutes', 'secondary'),
  ('Back Extension (Hyperextension)', 'glutes', 'secondary'),
  ('Back Extension (Hyperextension)', 'hamstrings', 'secondary'),
  ('Face Pull', 'upper_back_traps', 'secondary'),
  ('Face Pull', 'mid_back', 'secondary'),
  ('Rear Delt Reverse Fly (Machine)', 'mid_back', 'secondary'),
  ('Low Cable Fly Crossover', 'front_delt', 'secondary');

-- Same lockdown as the core schema, and keep future tables from inheriting Supabase's default grants.
alter table muscles enable row level security;
alter table library_exercises enable row level security;
alter table library_muscles enable row level security;
revoke all on muscles, library_exercises, library_muscles from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated;
