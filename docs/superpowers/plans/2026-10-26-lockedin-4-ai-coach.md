# LockedIn Plan 4 — AI Coach

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Coach page where the owner chats about their training. Claude reads their data through safe tools (never raw data in the prompt). It answers with concrete sessions and weights, remembers goals, and checks in on them every 4–6 weeks.

**Architecture:**
- **Backend:**
  - A `lockedin/coach/` package: tool implementations, a read-only SQL runner, a prompt, and a provider-neutral `CoachLLM` adapter. The real adapter wraps the Anthropic SDK; tests use a scripted fake.
  - The agentic loop is manual and streams to the browser as Server-Sent Events.
  - Conversations are stored append-only: full content blocks, including thinking and tool blocks, so history replays unchanged.
  - Goals live in a `goals` table. Only the `save_goal` tool writes, and only after the owner agrees.
- **Frontend:** a Coach page with a conversation list, a streaming chat, tool-progress chips and an active-goals panel.

**Tech:** Anthropic Python SDK (`anthropic`), model from `ANTHROPIC_MODEL`, default `claude-opus-5-5`, adaptive thinking (omitted param), `output_config.effort` `"medium"`. Server-side refusal fallbacks are on by default: beta `server-side-fallback-2026-07-01` + `fallbacks: "default"`. Prompt caching uses top-level `cache_control`. Tools have `eager_input_streaming: true`, with inputs validated before running.

**Spec:** `docs/superpowers/specs/2026-10-25-lockedin-design.md` §5.7.

## Global Constraints

- **Secrets:** `ANTHROPIC_API_KEY` is read only on the server. When it's missing, `/api/coach/*` chat returns 503 `"The coach isn't set up yet: add ANTHROPIC_API_KEY in Vercel."`
- **Database access:**
  - The coach's SQL runs as Postgres role `coach_ro`: SELECT-only grants plus RLS `for select to coach_ro using (true)` policies on whitelisted tables.
  - It runs on its own connection in a `READ ONLY` transaction with `statement_timeout = 3s`, and is always rolled back.
  - Only one statement is allowed, starting with `select` or `with`.
  - Results are capped at 200 rows and 20,000 characters of JSON.
- **Writes:**
  - Goals are written only via the `save_goal` tool. The system prompt requires explicit owner agreement in the conversation first.
  - `mark_goals_reviewed` only updates `profile.last_goal_review_at`.
- **Coaching tone** (spec anti-goals): no guilt; restart small after gaps; conservative weights for new exercises; no medical advice beyond common sense (pain or injury → see a professional).
- **History is append-only:** never edit or delete stored turns (preserved-thinking rules).
- **Vercel:** `maxDuration` 300 for the API function; responses stream.
- **UI:** all Plan 3 UI constraints apply (Night Shift, reduced motion, 375 px).

## Review Focus

1. **SQL tool escape attempts:** `insert`, `update`, `delete`, `drop`, `set role`, `select … ; delete …`, `select set_config('role','postgres',true)`, `select pg_sleep(10)`, `select * from fit_files`, `select * from auth.users`. Each must return an error result, never side effects or private tables. → Task 1 tests.
2. **Tool input garbage:** missing/extra fields, wrong types, a huge query string → an `is_error` tool_result with a clear message; the loop continues. → Task 2 tests.
3. **Loop limits:** at most 8 tool rounds per user message, then a final answer without tools. `max_tokens`, refusal and API errors produce a visible error event, not a hang. → Task 2 tests.
4. **Conversation replay:** the second message in a conversation sends the stored history unchanged (same blocks, same order) plus the new turn. → Task 3 test.
5. **A missing API key or provider outage** → a friendly 503 or error event; the rest of the app keeps working. → Task 3 test.

---

### Task 1: Schema, read-only SQL runner, data tools

**Files:**
- Create: `supabase/migrations/20261027000001_coach.sql`, `lockedin/coach/__init__.py`, `lockedin/coach/sql.py`, `lockedin/coach/tools.py`
- Test: `tests/test_coach_sql.py`, `tests/test_coach_tools.py`

**Interfaces:**
- **Migration:**
  - `goals (id bigint identity pk, text text not null, area text, target text, status text check in ('active','achieved','dropped') default 'active', source text default 'coach', created_at, updated_at)`
  - `coach_conversations (id bigint identity pk, title text, created_at, updated_at)`
  - `coach_messages (id bigint identity pk, conversation_id fk on delete cascade, role text check in ('user','assistant','system'), content jsonb not null, created_at)`
  - `profile.last_goal_review_at timestamptz`
  - RLS enabled on the new tables.
  - The role is created idempotently in a `do $$ … if not exists … create role coach_ro nologin; end $$`. Then `grant coach_ro to current_user`; `grant usage on schema public to coach_ro`.
  - SELECT on, and a `coach_read` policy for, these tables: `activities, gym_workouts, gym_sets, exercises, measurements, measurement_types, muscles, library_exercises, library_muscles, profile, goals`.
- **`lockedin/coach/sql.py`:**
  - `class QueryRejected(ValueError)`
  - `check_query(sql: str) -> str` returns the cleaned single statement (trailing `;` removed). It rejects:
    - empty input, or more than 4,000 chars
    - a `;` remaining after stripping the trailing one
    - anything not starting with `select` or `with` (case-insensitive, after comments are stripped)
  - `run_readonly(engine, sql: str, max_rows=200) -> dict` returns `{"columns": [...], "rows": [[...]], "row_count": n, "truncated": bool}`. Steps:
    - open a new connection;
    - `SET TRANSACTION READ ONLY`, then `SET LOCAL ROLE coach_ro`, then `SET LOCAL statement_timeout = '3s'`;
    - run `select * from (<sql>) as q limit <max_rows+1>`;
    - roll back.
    - Values are made JSON-safe (dates → ISO, Decimals → float). Postgres errors become a `QueryRejected` carrying the Postgres message.
- **`lockedin/coach/tools.py`:**
  - `TOOLS: list[dict]`: Anthropic tool definitions with `input_schema` (`additionalProperties: false`, `required`) and `eager_input_streaming: True`.
  - `SCHEMA_TEXT: str`: a curated description of the whitelisted tables and columns, with units and meanings (counted sessions rule, Brussels weeks, e1RM, dumbbell pair totals, zones).
  - `execute_tool(name: str, args: object, *, conn, engine, now) -> tuple[str, bool]` returns `(content, is_error)`:
    - `get_schema` `{}` → `SCHEMA_TEXT`
    - `run_sql` `{query: str}` → JSON from `run_readonly`
    - `get_focus_facts` `{}` → JSON of `focus_facts(conn, now)` (Plan 2)
    - `get_goals` `{}` → JSON list of all goals
    - `save_goal` `{action: "create"|"update"|"achieved"|"dropped", text?: str, area?: str, target?: str, goal_id?: int}`:
      - `create` needs `text`; the others need `goal_id`.
      - It also sets `profile.last_goal_review_at = now`.
      - Returns the saved goal as JSON.
    - `mark_goals_reviewed` `{}` → sets `last_goal_review_at`, returns `"ok"`.
    - An unknown tool name, or args failing validation, return `(message, True)`.

- [ ] **Step 1: Write failing tests:**
  - **`check_query`:** accepts `select 1`, `with x as (select 1) select * from x;` and a leading `-- comment`. Rejects:
    - `delete from goals`
    - `select 1; delete from goals`
    - `set role postgres`
    - `''`
    - 5,000 chars
  - **`run_readonly` on the test DB:**
    - `select count(*) from activities` works.
    - `select * from fit_files` → QueryRejected (permission denied).
    - `select set_config('role','postgres',true)` → rejected.
    - `select pg_sleep(5)` → rejected within about 3.5 s.
    - A writable-looking CTE `with d as (delete from goals returning *) select * from d` → rejected (read-only transaction).
    - 250 rows of `generate_series` → 200 rows, `truncated: true`.
    - Dates are serialized as ISO strings.
  - **`execute_tool`:**
    - `get_goals` → `[]`.
    - `save_goal` create → stored, `last_goal_review_at` set; `achieved` → status changed; `create` without text → error; unknown id → error.
    - Unknown tool → error.
    - `run_sql` with `{"query": 5}` → error.
    - `get_focus_facts` returns JSON with a `coverage` key.
- [ ] **Step 2–4:** RED → implement → GREEN.
- [ ] **Step 5: Commit** `feat(coach): goals and conversations schema, read-only SQL runner and tools`.

### Task 2: Coach loop with an LLM adapter

**Files:**
- Create: `lockedin/coach/prompt.py`, `lockedin/coach/llm.py`, `lockedin/coach/loop.py`
- Test: `tests/test_coach_loop.py`

**Interfaces:**
- **`prompt.py`:**
  - `SYSTEM_PROMPT: str` is static, for caching. It covers:
    - role: a personal coach for this one owner across bike, run, swim and gym
    - always ground claims in tools (focus facts first, then SQL); never invent numbers
    - give concrete sessions with weights, reps and zones
    - follow the tone rules from Global Constraints
    - goals: read them with `get_goals`; propose changes, but call `save_goal` only after the owner explicitly agrees in this conversation
    - check-in: when the context says a goal check-in is due, ask briefly at a natural point and call `mark_goals_reviewed` once done
    - dumbbell weights follow `profile.dumbbell_weights`
    - answer concisely, in short markdown (bold, bullet lists), no tables wider than 4 columns
  - `turn_context(conn, now) -> str` gives today's date (Brussels), the weekday, whether a goal check-in is due (`last_goal_review_at` null or 28+ days ago) and the active-goal count.
- **`llm.py`:**
  - `@dataclass class Final(content: list[dict], stop_reason: str)`
  - `class CoachLLM(Protocol): def stream(self, *, system: str, messages: list[dict], tools: list[dict]) -> Iterator[dict | Final]` yields `{"type": "text", "text": ...}` deltas, then a `Final` last.
  - `class AnthropicLLM(CoachLLM)`:
    - Uses `anthropic.Anthropic().beta.messages.stream(model=…, max_tokens=64000, system=[{"type":"text","text":system}], messages=…, tools=…, cache_control={"type":"ephemeral"}, output_config={"effort": "medium"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")`.
    - Yields text deltas, then `Final([b.to_dict() for b in final.content], final.stop_reason)`.
- **`loop.py`:** `run_turn(llm, *, history: list[dict], user_text: str, context: str, tool_runner: Callable[[str, object], tuple[str, bool]], max_rounds=8) -> Iterator[dict]` yields events:
  - `{"type": "text", "text"}`
  - `{"type": "tool", "name", "status": "start"|"done"|"error"}`
  - `{"type": "appended", "message": {...}}` for every message added to history (user, the context system message, assistant, tool_result user), so the caller persists exactly what was sent
  - `{"type": "done"}` or `{"type": "error", "message"}`

  Logic:
  - Append the user message, then a mid-conversation `{"role": "system", "content": context}`. The system message is allowed after a user message and before the assistant turn.
  - Loop:
    - Stream, then append the assistant content.
    - `refusal` → error "I can't help with that one."
    - `max_tokens` → error "That answer got too long; try a narrower question."
    - No `tool_use` → done.
    - Otherwise run every tool through `tool_runner` (validated inside it) and append all results in one user message.
    - After `max_rounds`, append a system message `"Answer now with what you have; no more tools."` and stream once more with `tools` still sent (the history contains tool blocks).
- [ ] **Step 1: Write failing tests** with a scripted `FakeLLM` (a list of scripted turns; it records the `messages` it receives):
  - A text-only answer streams text, then done; history gains user, system and assistant.
  - One tool round: tool start and done events, the tool_result is matched by `tool_use_id`, and the second call's messages contain the assistant `tool_use` content unchanged.
  - Two tool_use blocks in one turn → both results in one user message.
  - A tool error → `is_error: true`, and the loop continues.
  - Refusal → error event.
  - 9 tool rounds → exactly 8 executed, then the "answer now" system message and the final answer.
  - An LLM exception → an error event with a friendly message.
- [ ] **Step 2–4:** RED → implement → GREEN.
- [ ] **Step 5: Commit** `feat(coach): streaming tool loop with a pluggable LLM adapter`.

### Task 3: Coach API (conversations, streaming messages, goals)

**Files:**
- Create: `lockedin/routes/coach.py`
- Modify: `lockedin/app.py`, `requirements.txt` / `pyproject.toml` (`anthropic`), `vercel.json` (`maxDuration` 300), `.env.example`
- Test: `tests/test_routes_coach.py`

**Interfaces:** all owner-only.
- Dependencies:
  - `get_llm() -> CoachLLM` raises 503 when `ANTHROPIC_API_KEY` is unset.
  - `get_coach_engine() -> Engine` is the app engine; tests override it with the test engine.
- `GET /api/coach/conversations` → `[{"id", "title", "updated_at"}]`, newest first.
- `POST /api/coach/conversations` → `{"id"}` (201).
- `GET /api/coach/conversations/{id}` → `{"id", "title", "messages": [{"role", "text", "tools": [names]}]}`. This is a display view: the text blocks of user and assistant messages, the names of tool calls, and no system messages or tool results. 404 when unknown.
- `POST /api/coach/conversations/{id}/messages` with body `{"text": str (1–4000)}`:
  - Returns a `text/event-stream` with `data: <json>\n\n` per loop event (`appended` events are not sent to the browser).
  - Each appended message is persisted in its own short transaction as it happens.
  - The first user text (truncated to 60 chars) becomes the title.
  - `updated_at` is bumped.
- `GET /api/coach/goals` → `[goal]`, with active ones first.
- [ ] **Step 1: Write failing tests** (FakeLLM injected via dependency override):
  - Create a conversation, post a message, and parse the SSE events: text, then done.
  - The stored messages are user + system + assistant in order.
  - The display view shows user text and assistant text.
  - A second message sends the previous history unchanged as the prefix (FakeLLM's recorded `messages`).
  - The title is set.
  - Goals list.
  - Missing key → 503 on post message.
  - Unknown conversation → 404.
  - All routes → 401 without a token.
- [ ] **Step 2–4:** RED → implement → GREEN.
- [ ] **Step 5: Commit** `feat(coach): conversations API with streamed answers`.

### Task 4: Coach page

**Files:**
- Create: `web/src/pages/Coach.tsx`, `web/src/lib/markdown.tsx` (a tiny safe renderer), `web/src/lib/sse.ts` (POST + read SSE events)
- Modify: `web/src/App.tsx` (route `/coach`, `/coach/:id`), `web/src/components/Layout.tsx` (a "Coach" nav item; the tab bar gets 6 columns), `web/src/styles.css`
- Test: `web/src/lib/markdown.test.tsx`, `web/src/lib/sse.test.ts`

**Interfaces:**
- **`renderMarkdown(text: string): ReactNode`** supports paragraphs, `**bold**`, `*italic*`, `- `/`1. ` lists, `### ` headings and inline code. It never uses `dangerouslySetInnerHTML`, so raw HTML stays as text.
- **`parseSSE(chunk: string, carry: string): { events: unknown[]; carry: string }`** splits on blank lines and JSON-parses `data:` lines.
- **Page layout:**
  - **Desktop:** a left column with "New chat" and the conversation list, plus an "Active goals" card.
  - **Main area:**
    - message list, with user bubbles on the right and assistant text on the left
    - streaming text with a blinking caret (reduced motion: no blink)
    - tool chips like "Checking your rides…" mapped from tool names
    - a textarea (Enter sends, Shift+Enter adds a newline) and a Send button
  - **Phone:** the list collapses into a select at the top.
- **Starter prompts** on an empty conversation:
  - "What should I focus on this week?"
  - "Plan my next gym session"
  - "Am I getting fitter on the bike?"
  - "Help me set goals"
- **Errors:** a 503 shows a setup message; a stream error shows "Something went wrong" with Retry.
- [ ] RED (markdown, SSE tests) → implement → GREEN; build passes.
- [ ] **Commit** `feat(web): coach chat page with streaming answers and goals`.

### Task 5: Verify, docs, review

- [ ] Run the local stack with the real data. When `ANTHROPIC_API_KEY` is available locally, have one real conversation:
  - "What should I focus on this week?" → it uses tools and cites real numbers.
  - "Set a goal: bench 100 kg by March" → it asks to confirm, then saves.
  - Without a key, verify the 503 setup message instead.
- [ ] Run Playwright at 1440 px and 375 px: page renders, starter prompt → a streamed answer (or the setup message), no console errors, no overflow.
- [ ] README: "AI coach" section (what it can see, the read-only guarantee, goals, cost note, env vars) and the deploy order (`supabase db push` → set `ANTHROPIC_API_KEY` in Vercel → `git push`).
- [ ] Run the full test suites and the build, then commit.
