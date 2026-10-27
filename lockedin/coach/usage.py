"""What the coach costs: per-call token usage, priced, and today's (Brussels) total against the daily budget."""

from datetime import datetime, time

from sqlalchemy import Connection, text

from lockedin.timeutil import TZ

# US dollars per million tokens: input, output, cache read. Cache writes (5-minute cache) cost 1.25x input.
# The models the coach runs on, and the ones a refused request can fall back to.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
}
UNKNOWN_PRICE = (10.00, 50.00, 1.00)  # a model not listed above is priced high, so the budget errs on the safe side
CACHE_WRITE = 1.25
FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def price(model: str) -> tuple[float, float, float]:
    match = max((m for m in PRICES if model == m or model.startswith(f"{m}-")), key=len, default=None)
    return PRICES[match] if match else UNKNOWN_PRICE


def cost(call: dict) -> float:
    inp, out, read = price(call["model"])
    n = {k: call.get(k) or 0 for k in FIELDS}
    return (n["input_tokens"] * inp + n["output_tokens"] * out + n["cache_read_tokens"] * read
            + n["cache_write_tokens"] * inp * CACHE_WRITE) / 1_000_000


def record(conn: Connection, conversation_id: int | None, calls: list[dict], now: datetime) -> None:
    for call in calls:
        conn.execute(text(
            "insert into coach.usage (conversation_id, model, input_tokens, output_tokens, cache_read_tokens, "
            "cache_write_tokens, cost_usd, created_at) values (:cid, :model, :input_tokens, :output_tokens, "
            ":cache_read_tokens, :cache_write_tokens, :cost, :now)"),
            {**{k: call.get(k) or 0 for k in FIELDS}, "model": call["model"], "cid": conversation_id,
             "cost": round(cost(call), 6), "now": now})


def spent_today(conn: Connection, now: datetime) -> float:
    midnight = datetime.combine(now.astimezone(TZ).date(), time.min, TZ)
    return float(conn.execute(text("select coalesce(sum(cost_usd), 0) from coach.usage where created_at >= :m"),
                              {"m": midnight}).scalar())
