-- Goals get a kind (so the app can steer by them); agenda items get run/swim targets and the goal they serve.
update goals set area = case
  when lower(coalesce(area, '')) ~ '(gym|strength|lift)' then 'gym'
  when lower(coalesce(area, '')) ~ '(bike|cycl|zwift|ride)' then 'bike'
  when lower(coalesce(area, '')) ~ 'run' then 'run'
  when lower(coalesce(area, '')) ~ 'swim' then 'swim'
  when lower(coalesce(area, '')) ~ '(body|weight)' then 'body'
  else 'general' end;
alter table goals alter column area set default 'general';
alter table goals alter column area set not null;
alter table goals add constraint goals_area_check check (area in ('gym', 'bike', 'run', 'swim', 'body', 'general'));

alter table agenda_items
  add column targets jsonb,
  add column goal_id bigint references goals(id) on delete set null;
