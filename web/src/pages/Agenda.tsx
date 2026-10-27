import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { apiFetch } from "../lib/api";
import { SPORT_COLOR, SPORT_NAME, weekDays, type AgendaItem, type AgendaSport, type AgendaWeek } from "../lib/agenda";
import { formatDay } from "../lib/format";
import { stagger } from "../lib/motion";
import { shiftWeek } from "../lib/musclemap";
import type { PlanDays } from "../lib/plan";

const ZWIFT_TEXT = { synced: "In Zwift ✓", pending: "Goes to Zwift at the next sync" };

function ItemCard({ item, past, onOpen, i }: { item: AgendaItem; past: boolean; onOpen: () => void; i: number }) {
  const summary = item.done ? item.result : item.zwift?.summary ?? item.note;
  const notDone = past && !item.done && !["rest", "other"].includes(item.sport);
  return (
    <div className={`agenda-item rise${item.sport === "rest" ? " rest" : ""}${item.done ? " done" : ""}${notDone ? " missed" : ""}`}
      style={{ ["--c" as string]: SPORT_COLOR[item.sport], ...stagger(i, 0.03) }}>
      <button className="agenda-item-main" onClick={onOpen}>
        <span className="agenda-item-title">{item.done && <span className="tick" aria-label="Done">✓</span>}{item.title}</span>
        {summary && <span className="agenda-item-sub">{summary}</span>}
        <span className="agenda-pills">
          {notDone && <span className="pill">Not done</span>}
          {item.goal && <span className="pill goal">{item.goal}</span>}
          {item.zwift_status && !item.done && <span className={`pill zwift ${item.zwift_status}`}>{ZWIFT_TEXT[item.zwift_status]}</span>}
          {item.optional && <span className="pill optional">Optional</span>}
        </span>
      </button>
      {item.sport === "gym" && item.routine && !past && (
        <Link className="agenda-plan-link" to={`/plan?day=${encodeURIComponent(item.routine)}`}>Plan it →</Link>
      )}
    </div>
  );
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close.current(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); opener?.focus(); };
  }, []);
  return (
    <div className="sheet-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} className="sheet pop" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row spread" style={{ marginBottom: 6 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button className="btn small ghost" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function AddSheet({ day, onDone, onClose }: { day: string; onDone: () => void; onClose: () => void }) {
  const [routines, setRoutines] = useState<string[]>([]);
  const [form, setForm] = useState<{ sport: AgendaSport; title: string; note: string; optional: boolean; routine: string }>(
    { sport: "gym", title: "", note: "", optional: false, routine: "" });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiFetch<PlanDays>("/api/plan/days").then((d) => {
      const names = d.days.map((x) => x.title);
      setRoutines(names);
      setForm((f) => (f.sport === "gym" && !f.routine && names[0] ? { ...f, routine: names[0], title: f.title || names[0] } : f));
    }).catch(() => undefined);
  }, []);
  const setSport = (sport: AgendaSport) => setForm((f) => ({
    ...f, sport,
    title: sport === "rest" ? "Rest" : sport === "gym" && f.routine ? f.routine
      : f.title === "Rest" || (f.sport === "gym" && f.title === f.routine) ? "" : f.title,
  }));
  const add = (e: FormEvent) => {
    e.preventDefault();
    const body = { day, sport: form.sport, title: form.title.trim(), note: form.note.trim() || null, optional: form.optional,
      routine: form.sport === "gym" && form.routine ? form.routine : null };
    apiFetch("/api/agenda", { method: "POST", body: JSON.stringify(body) }).then(onDone).catch((err) => setError(err.message));
  };
  return (
    <Sheet title={`Add to ${formatDay(day, { weekday: "long", day: "numeric", month: "short" })}`} onClose={onClose}>
      <form onSubmit={add} className="stack">
        <label className="field">What
          <select value={form.sport} onChange={(e) => setSport(e.target.value as AgendaSport)}>
            <option value="gym">Gym: one of your routines</option>
            <option value="run">Run</option>
            <option value="swim">Swim</option>
            <option value="bike">Zwift ride (note only)</option>
            <option value="rest">Rest</option>
            <option value="other">Other</option>
          </select>
        </label>
        {form.sport === "gym" && (
          <label className="field">Routine
            <select value={form.routine} onChange={(e) => setForm({ ...form, routine: e.target.value, title: e.target.value })}>
              {routines.length === 0 && <option value="">No Hevy routines yet</option>}
              {routines.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
        )}
        <label className="field">Title<input value={form.title} maxLength={80} required onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="field">Note<input value={form.note} maxLength={500} placeholder="optional" onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
        <label className="row" style={{ gap: 8, fontSize: 14 }}>
          <input type="checkbox" checked={form.optional} onChange={(e) => setForm({ ...form, optional: e.target.checked })} /> Optional
        </label>
        {form.sport === "bike" && <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>Workouts with power targets come from the coach: ask it in chat and it puts them in Zwift too.</p>}
        {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <div className="row"><button className="btn primary" type="submit">Add</button></div>
      </form>
    </Sheet>
  );
}

export default function Agenda() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("week");
  const week = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null;
  const [data, setData] = useState<AgendaWeek | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const navigate = useNavigate();

  const [reloads, setReloads] = useState(0);
  useEffect(() => {
    let current = true;  // a slower, older week must not overwrite the one asked for last
    setError(null);
    apiFetch<AgendaWeek>(`/api/agenda${week ? `?week=${week}` : ""}`)
      .then((d) => { if (current) setData(d); })
      .catch((e) => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [week, reloads]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  const days = weekDays(data.week_start);
  const range = `${formatDay(days[0], { day: "numeric", month: "short" })} – ${formatDay(days[6], { day: "numeric", month: "short" })}`;
  const isThisWeek = days.includes(data.today);
  const done = () => { setAdding(null); setReloads((n) => n + 1); };
  const from = week ?? data.week_start;  // from the URL, so quick clicks add up before the data arrives
  const training = data.items.filter((i) => !["rest", "other"].includes(i.sport));

  return (
    <>
      <PageHeader eyebrow={isThisWeek ? `This week · ${training.length} sessions planned` : `${training.length} sessions planned`} title="Agenda"
        right={<div className="row" style={{ gap: 8 }}>
          <button className="btn" aria-label="Previous week" onClick={() => setParams({ week: shiftWeek(from, -1) })}>‹</button>
          <span className="agenda-range">{range}</span>
          <button className="btn" aria-label="Next week" onClick={() => setParams({ week: shiftWeek(from, 1) })}>›</button>
          {!isThisWeek && <button className="btn" onClick={() => setParams({})}>Today</button>}
          <Link to="/coach" className="btn primary">Plan with coach</Link>
        </div>} />
      <div className="legend">
        {(["bike", "gym", "run", "swim", "rest"] as AgendaSport[]).map((s) => (
          <span key={s}><i className="swatch" style={{ background: SPORT_COLOR[s] }} />{s === "bike" ? "Zwift" : SPORT_NAME[s]}</span>
        ))}
      </div>
      <div className="agenda-week">
        {days.map((d, n) => {
          const items = data.items.filter((i) => i.day === d);
          const past = d < data.today;
          const long = formatDay(d, { weekday: "long" });
          return (
            <section key={d} className={`agenda-day${d === data.today ? " today" : ""}${past ? " past" : ""}`}
              aria-label={`${formatDay(d, { weekday: "short" })} ${formatDay(d, { day: "numeric", month: "short" })}`}>
              <div className="agenda-day-head">
                <b>{formatDay(d, { weekday: "short" })}</b>
                <span>{formatDay(d, { day: "numeric" })}{d === data.today ? " · today" : ""}</span>
              </div>
              <div className="agenda-day-items">
                {items.map((it, i) => <ItemCard key={it.id} item={it} past={past} i={n + i} onOpen={() => navigate(`/agenda/${it.id}`)} />)}
                <button className="agenda-add" aria-label={`Add to ${long}`} onClick={() => setAdding(d)}>+ Add</button>
              </div>
            </section>
          );
        })}
      </div>
      {data.items.length === 0 && (
        <p className="muted" style={{ margin: 0 }}>Nothing planned this week. Work out a plan with the coach and say "put it in my agenda", or add sessions yourself.</p>
      )}
      {adding && <AddSheet day={adding} onDone={done} onClose={() => setAdding(null)} />}
    </>
  );
}
