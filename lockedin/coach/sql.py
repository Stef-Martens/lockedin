"""The coach's SQL tool: one SELECT, run as coach_ro in a read-only transaction, small JSON-safe results."""

import json
import re

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

MAX_QUERY_CHARS = 4000
MAX_RESULT_CHARS = 20_000
TIMEOUT = "3s"

COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


class QueryRejected(ValueError):
    pass


def check_query(sql: str) -> str:
    """The query as one statement without its trailing semicolon, or QueryRejected."""
    cleaned = sql.strip().rstrip(";").rstrip()
    if not cleaned:
        raise QueryRejected("The query is empty.")
    if len(cleaned) > MAX_QUERY_CHARS:
        raise QueryRejected(f"The query is longer than {MAX_QUERY_CHARS} characters; simplify it.")
    if ";" in cleaned:
        raise QueryRejected("Only one statement is allowed; remove the semicolons.")
    words = COMMENTS.sub(" ", cleaned).split()
    if not words or words[0].lower() not in ("select", "with"):
        raise QueryRejected("Only SELECT (or WITH ... SELECT) queries are allowed.")
    return cleaned


def run_readonly(engine: Engine, sql: str, max_rows: int = 200) -> dict:
    query = check_query(sql)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("set transaction read only")
            conn.exec_driver_sql(f"set local statement_timeout = '{TIMEOUT}'")
            conn.exec_driver_sql("set local time zone 'Europe/Brussels'")
            raw = conn.execute(text("select coach.run_query(:q, :n)::text"), {"q": query, "n": max_rows + 1}).scalar_one()
            conn.rollback()
    except DBAPIError as e:
        message = str(e.orig).splitlines()[0] if e.orig else str(e)
        raise QueryRejected(f"Postgres said: {message}") from None
    # Pairs, not dicts: keeps column order and duplicate names.
    records = json.loads(raw, object_pairs_hook=lambda pairs: pairs)
    columns = [k for k, _ in records[0]] if records else []
    rows = [[v for _, v in r] for r in records]
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    while rows and len(json.dumps(rows)) > MAX_RESULT_CHARS:
        rows = rows[: len(rows) // 2]
        truncated = True
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}
