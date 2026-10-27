import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, PageHeader } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { renderMarkdown } from "../lib/markdown";
import { stagger } from "../lib/motion";
import { postStream } from "../lib/sse";

interface Conversation { id: number; title: string | null; updated_at: string }
interface ChatMessage { role: "user" | "assistant"; text: string; tools: string[] }
interface Goal { id: number; text: string; area: string | null; target: string | null; status: "active" | "achieved" | "dropped" }
type CoachEvent =
  | { type: "text"; text: string }
  | { type: "tool"; name: string; status: "start" | "done" | "error" }
  | { type: "done" }
  | { type: "reset" }
  | { type: "error"; message: string };

const TOOL_ACTIVE: Record<string, string> = {
  get_schema: "Looking at your data…",
  run_sql: "Checking your numbers…",
  get_focus_facts: "Reading your focus points…",
  get_goals: "Checking your goals…",
  save_goal: "Saving your goal…",
  mark_goals_reviewed: "Noting the goal check-in…",
};
const TOOL_DONE: Record<string, string> = {
  get_schema: "your data", run_sql: "your numbers", get_focus_facts: "your focus points",
  get_goals: "your goals", save_goal: "saved a goal", mark_goals_reviewed: "goal check-in",
};
const STARTERS = [
  "What should I focus on this week?",
  "Plan my next gym session",
  "Am I getting fitter on the bike?",
  "Help me set goals",
];

function grow(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
}

function usedLine(tools: string[]): string | null {
  const names = [...new Set(tools.map((t) => TOOL_DONE[t] ?? t))];
  return names.length ? `Looked at ${names.join(" · ")}` : null;
}

function Bubble({ m, live, activity }: { m: ChatMessage; live?: boolean; activity?: string | null }) {
  if (m.role === "user") return <div className="msg user pop">{m.text}</div>;
  const used = usedLine(m.tools);
  return (
    <div className="msg assistant">
      {used && !live && <div className="msg-used">{used}</div>}
      {m.text && <div className="md">{renderMarkdown(m.text)}{live && !activity && <span className="caret" aria-hidden="true" />}</div>}
      {live && activity && <div className="msg-activity shimmer">{activity}</div>}
      {live && !activity && !m.text && <div className="msg-activity shimmer">Thinking…</div>}
    </div>
  );
}

function Goals({ goals }: { goals: Goal[] }) {
  const active = goals.filter((g) => g.status === "active");
  return (
    <>
      <h2>Goals</h2>
      {active.length ? (
        <ul className="goal-list">
          {active.map((g) => (
            <li key={g.id}><span>{g.text}</span>{g.target && <span className="muted"> · {g.target}</span>}</li>
          ))}
        </ul>
      ) : (
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>No goals yet. Ask the coach to help you set some.</p>
      )}
    </>
  );
}

export default function Coach() {
  const { id } = useParams();
  const cid = id ? Number(id) : null;
  const navigate = useNavigate();
  const [list, setList] = useState<Conversation[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [live, setLive] = useState<ChatMessage | null>(null);
  const [liveFor, setLiveFor] = useState<number | null>(null);  // the chat the live answer belongs to
  const [activity, setActivity] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<{ message: string; retry?: string } | null>(null);
  const [setup, setSetup] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const created = useRef<number | null>(null);
  // The answer being streamed; leaving the Coach page stops reading it.
  const streaming = useRef<AbortController | null>(null);
  useEffect(() => () => streaming.current?.abort(), []);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const busy = live !== null;
  const viewing = useRef(cid);
  viewing.current = cid;

  const refreshSide = useCallback(() => {
    apiFetch<Conversation[]>("/api/coach/conversations").then(setList).catch(() => undefined);
    apiFetch<Goal[]>("/api/coach/goals").then(setGoals).catch(() => undefined);
  }, []);
  useEffect(refreshSide, [refreshSide]);
  useEffect(() => {  // say so up front when there's no API key, instead of after the first message
    apiFetch<{ ready: boolean }>("/api/coach/status")
      .then((s) => { if (!s.ready) setSetup("The coach isn't set up yet: add ANTHROPIC_API_KEY in Vercel."); })
      .catch(() => undefined);
  }, []);

  const load = useCallback((chat: number) =>
    apiFetch<{ messages: ChatMessage[] }>(`/api/coach/conversations/${chat}`)
      .then((c) => { if (viewing.current === chat) setMessages(c.messages); }), []);

  useEffect(() => {
    setError(null);
    if (cid === null) { setMessages([]); return; }
    if (created.current === cid) { created.current = null; return; }  // we just made it and are streaming into it
    setLoading(true);
    load(cid).catch((e) => setError({ message: e.message })).finally(() => setLoading(false));
  }, [cid, load]);

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView?.({ block: "end", behavior: reduced ? "auto" : "smooth" });
  }, [messages.length, live?.text.length, activity]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setError(null);
    setDraft("");
    if (inputRef.current) inputRef.current.style.height = "";
    setMessages((ms) => [...ms, { role: "user", text: message, tools: [] }]);
    let current: ChatMessage = { role: "assistant", text: "", tools: [] };
    let afterTool = false;
    let roundStart = 0;  // where this round's text began, so a restarted round can be dropped
    setLive(current);
    let target = cid;
    setLiveFor(target);
    let failed: string | null = null;
    let ended = false;
    let notSetUp = false;
    const ctrl = new AbortController();
    streaming.current = ctrl;
    const signal = ctrl.signal;
    try {
      if (target === null) {
        target = (await apiFetch<{ id: number }>("/api/coach/conversations", { method: "POST", signal })).id;
        created.current = target;
        setLiveFor(target);
        navigate(`/coach/${target}`, { replace: true });
        refreshSide();
      }
      await postStream(`/api/coach/conversations/${target}/messages`, { text: message }, (raw) => {
        const e = raw as CoachEvent;
        if (e.type === "text") {
          current = { ...current, text: current.text + (afterTool && current.text ? "\n\n" : "") + e.text };
          afterTool = false;
          setActivity(null);
        } else if (e.type === "reset") {
          current = { ...current, text: current.text.slice(0, roundStart) };
        } else if (e.type === "tool") {
          if (e.status === "start") setActivity(TOOL_ACTIVE[e.name] ?? "Working…");
          else { current = { ...current, tools: [...current.tools, e.name] }; afterTool = true; roundStart = current.text.length; }
        } else if (e.type === "error") failed = e.message;
        if (e.type === "done" || e.type === "error") ended = true;
        setLive(current);
      }, signal);
    } catch (e) {
      if (signal.aborted) return;  // left the page: nothing to show or reload
      if (e instanceof ApiError && e.status === 503) { setSetup(e.detail); notSetUp = true; }
      else failed = e instanceof Error ? e.message : "Something went wrong.";
    }
    if (streaming.current === ctrl) streaming.current = null;
    if (!failed && !ended && !notSetUp) failed = "The connection dropped. Try again.";
    setActivity(null);
    setLive(null);
    refreshSide();
    if (viewing.current !== target) return;  // the owner moved to another chat meanwhile
    if (failed) {
      setError({ message: failed, retry: message });
      // Part of a failed turn may or may not have been stored; show exactly what was.
      if (target !== null) load(target).catch(() => undefined);
      else setMessages((ms) => ms.slice(0, -1));
    } else if (notSetUp || !current.text) setMessages((ms) => ms.slice(0, -1));
    else setMessages((ms) => [...ms, current]);
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    }
  }

  const empty = !loading && messages.length === 0 && !live;

  return (
    <>
      <PageHeader eyebrow="AI coach" title="Coach" sub="Ask about your training. It reads your data and remembers your goals."
        right={<Link to="/coach" className="btn" onClick={() => { setMessages([]); setError(null); }}>New chat</Link>} />

      <div className="coach">
        <aside className="coach-side">
          <Card i={1} className="coach-convos">
            <h2>Chats</h2>
            {list.length ? (
              <ul className="list">
                {list.map((c) => (
                  <li key={c.id}>
                    <Link to={`/coach/${c.id}`} className={`convo-link${c.id === cid ? " active" : ""}`}>
                      {c.title ?? "New chat"}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="muted" style={{ margin: 0, fontSize: 14 }}>Your chats will show up here.</p>}
          </Card>
          <Card i={2}><Goals goals={goals} /></Card>
        </aside>

        <div className="coach-phone-bar rise">
          <label className="field" style={{ flex: 1 }}>
            <span className="sr-only">Chat</span>
            <select value={cid ?? ""} onChange={(e) => navigate(e.target.value ? `/coach/${e.target.value}` : "/coach")}>
              <option value="">New chat</option>
              {list.map((c) => <option key={c.id} value={c.id}>{c.title ?? "New chat"}</option>)}
            </select>
          </label>
          <details className="coach-goals">
            <summary className="chip">Goals · {goals.filter((g) => g.status === "active").length}</summary>
            <div className="card coach-goals-pop"><Goals goals={goals} /></div>
          </details>
        </div>

        <Card i={1} className="coach-chat">
          {setup && <div className="note accent">{setup}</div>}
          {loading && <p className="muted">Loading…</p>}
          {empty && !setup && (
            <div className="coach-empty">
              <p className="secondary" style={{ margin: 0 }}>Start with one of these, or ask anything.</p>
              <div className="chips">
                {STARTERS.map((s, n) => (
                  <button key={s} className="chip rise" style={stagger(n, 0.06, 0.15)} onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          <div className="msgs" aria-live="polite">
            {messages.map((m, n) => <Bubble key={n} m={m} />)}
            {live && liveFor === cid && <Bubble m={live} live activity={activity} />}
          </div>
          {error && (
            <div className="note row spread" role="alert">
              <span className="error">{error.message}</span>
              {error.retry && !setup && <button className="btn" onClick={() => send(error.retry!)}>Retry</button>}
            </div>
          )}
          <div ref={endRef} />
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
            <label className="sr-only" htmlFor="coach-input">Message the coach</label>
            <textarea id="coach-input" ref={inputRef} rows={1} value={draft} maxLength={4000} placeholder="Ask your coach…"
              onChange={(e) => { setDraft(e.target.value); grow(e.target); }} onKeyDown={onKey} disabled={!!setup} />
            <button className="btn primary" type="submit" disabled={busy || !draft.trim() || !!setup}>Send</button>
          </form>
        </Card>
      </div>
    </>
  );
}
