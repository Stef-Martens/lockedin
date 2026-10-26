-- Goals saved before goals had a kind ended up as 'general'. Guess the kind from the goal's own words so the
-- app can steer by it; the coach can still change it.
update goals set area = case
  when lower(text) ~ '(bench|squat|deadlift|press|curl|row|pull.?up|chin.?up|lift|1rm)' then 'gym'
  when lower(text) ~ '(ftp|watt|\d+\s*w\M|zwift|bike|cycl|ride)' then 'bike'
  when lower(text) ~ '(swim|pool|freestyle)' then 'swim'
  when lower(text) ~ '(\d+\s*k\M|\d+\s*km|run|marathon|5k|10k)' then 'run'
  when lower(text) ~ '(weight|waist|chest|arm|thigh|hips|shoulders|body fat)' then 'body'
  else area end
where area = 'general';
