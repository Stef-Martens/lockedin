-- The coach's query function: cap the result size and pin pg_temp last in the search path.
create or replace function coach.run_query(sql text, max_rows integer) returns json
language plpgsql security definer
set search_path = public, pg_temp
as $$
declare result json;
begin
  -- Newlines keep a trailing "--" comment in the query from swallowing the wrapper.
  execute format(E'select coalesce(json_agg(r), ''[]''::json) from (select * from (\n%s\n) q limit %s) r',
                 sql, max_rows) into result;
  if octet_length(result::text) > 1000000 then
    raise exception 'Result too large; select fewer or shorter columns, or aggregate.';
  end if;
  return result;
end $$;
