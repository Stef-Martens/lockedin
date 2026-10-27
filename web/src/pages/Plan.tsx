import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, PageHeader } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { shortDay } from "../lib/format";
import { stagger } from "../lib/motion";
import { useApi } from "../lib/useApi";
import { changeLabel, doseLine, lastLine, type Plan as PlanData, type PlanDays, type PlanItem, type Preferences } from "../lib/plan";


function ItemMenu({ item, onAction }: { item: PlanItem; onAction: (action: "skip" | "never") => void }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const wrap = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector("button")?.focus();
    // Close on a tap elsewhere. (Not on blur: phone Safari doesn't focus a tapped button, so blur would close
    // the menu before the tap on an item lands.)
    const outside = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const close = () => { setOpen(false); button.current?.focus(); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); return; }
    const items = [...(menu.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: items.length - 1 }[e.key];
    if (next === undefined || !items.length) return;
    e.preventDefault();
    items[(next + items.length) % items.length].focus();
  };
  const choose = (action: "skip" | "never") => { close(); onAction(action); };
  return (
    <span className="plan-menu" ref={wrap}>
      <button ref={button} className="btn small ghost" aria-label={`More for ${item.exercise}`} aria-haspopup="menu"
        aria-expanded={open} onClick={() => setOpen((o) => !o)}>⋯</button>
      {open && (
        <div ref={menu} className="plan-menu-pop pop" role="menu" onKeyDown={onKey}>
          <button role="menuitem" onClick={() => choose("skip")}>{item.skipped ? "Undo skip" : "Skip for today"}</button>
          {item.suggested && <button role="menuitem" onClick={() => choose("never")}>Don't suggest this again</button>}
        </div>
      )}
    </span>
  );
}

function ItemCard({ item, n, onAction }: { item: PlanItem; n: string; onAction: (action: "swap" | "skip" | "never") => void }) {
  const change = changeLabel(item);
  const last = lastLine(item);
  return (
    <div className={`plan-item rise${item.skipped ? " skipped" : ""}`}>
      <div className="plan-item-top">
        <span className="plan-n" aria-hidden="true">{n}</span>
        <div className="plan-name">
          {item.kind === "swap" && <span className="plan-tag variety">Variety</span>}
          {item.estimate && <span className="plan-tag new">New</span>}
          {item.exercise}
        </div>
        <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
          {item.muscle && <button className="btn small" aria-label={`Swap ${item.exercise}`} onClick={() => onAction("swap")}>Swap</button>}
          <ItemMenu item={item} onAction={onAction} />
        </div>
      </div>
      <div className="plan-body">
        <div className="plan-dose num">{doseLine(item)}</div>
        {!!item.lighter_sets && <div className="secondary" style={{ fontSize: 13 }}>plus {item.lighter_sets} lighter {item.lighter_sets === 1 ? "set" : "sets"} to build up, like last time</div>}
        {change && <div className={`plan-change ${item.change}`}>{change}</div>}
        {last && <div className="muted num" style={{ fontSize: 12.5 }}>{last}</div>}
        {item.replaces && <div className="secondary" style={{ fontSize: 13 }}>Instead of {item.replaces}</div>}
        {item.reason && <div className="secondary" style={{ fontSize: 13 }}>{item.reason}</div>}
        {item.goal && <div className="plan-goal">Goal: {item.goal}</div>}
      </div>
    </div>
  );
}

function DayPicker({ open }: { open: (params: Record<string, string>) => void }) {
  const [days, setDays] = useState<PlanDays | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { apiFetch<PlanDays>("/api/plan/days").then(setDays).catch((e) => setError(e.message)); }, []);
  if (error) return <p className="error">{error}</p>;
  if (!days) return <p className="muted">Loading…</p>;
  return (
    <>
      <PageHeader eyebrow="Going to the gym?" title="Plan a workout" sub="Pick your day; the app fills it in."
        right={<button className="btn" onClick={() => open({ prefs: "1" })}>Preferences</button>} />
      {days.comeback && <div className="note accent rise">Welcome back. Plans keep last time's weights for now; build up again from there.</div>}
      <div className="plan-days">
        {days.days.map((d, i) => (
          <button key={d.title} className="plan-day lift rise" style={stagger(i)} onClick={() => open({ day: d.title })}>
            <span className="plan-day-title">{d.title}</span>
            <span className="secondary">{d.exercise_count} exercises</span>
            <span className="plan-day-last">last done<br />{shortDay(d.last_done)}</span>
          </button>
        ))}
        {days.missed_available && (
          <button className="plan-day lift rise" style={stagger(days.days.length)} onClick={() => open({ missed: "1" })}>
            <span className="plan-day-title">Just what I've missed</span>
            <span className="secondary">the muscles you've trained least lately</span>
          </button>
        )}
      </div>
      {days.days.length === 0 && (
        <p className="muted">Your Hevy routines show up here once you've done them: start a workout from a routine in Hevy,
          then <Link to="/import">import your export</Link>.</p>
      )}
    </>
  );
}

function PlanView({ dayTitle, open }: { dayTitle: string | null; open: (params: Record<string, string>) => void }) {
  const query = dayTitle ? `?day=${encodeURIComponent(dayTitle)}` : "";
  // Switching days aborts the old day's plan, so it can't show up under the new title.
  const { data: plan, error: loadError, reload, setData: setPlan } = useApi<PlanData>(`/api/plan${query}`);
  const [rebuildError, setRebuildError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const act = (item: PlanItem) => (action: "swap" | "skip" | "never") => {
    setNotice(null);
    apiFetch<PlanData>(`/api/plan/${plan!.id}/items/${item.id}/${action}`, { method: "POST" })
      .then(setPlan)
      .catch((e) => {
        // The plan was rebuilt elsewhere (new day, new preferences): show the current one.
        if (e instanceof ApiError && e.status === 404) { reload(); return; }
        setNotice(e instanceof Error ? e.message : "That didn't work.");
      });
  };
  const rebuild = () => {
    setPlan(null);
    setRebuildError(null);
    apiFetch<PlanData>(`/api/plan/new${query}`, { method: "POST" }).then(setPlan).catch((e) => setRebuildError(e.message));
  };

  const back = <button className="link-btn" onClick={() => open({})}>‹ All days</button>;
  const error = loadError?.message ?? rebuildError;
  if (error) return <>{back}<p className="error">{error}</p></>;
  if (!plan) return <>{back}<p className="muted">Building your plan…</p></>;

  const main = plan.items.filter((i) => i.kind !== "add");
  const extra = plan.items.filter((i) => i.kind === "add");
  const working = main.filter((i) => !i.skipped).reduce((n, i) => n + i.sets, 0);
  return (
    <>
      {back}
      <PageHeader eyebrow={`${shortDay(plan.built_on)} · ${main.length} exercises · ${working} working sets`}
        title={plan.day ?? "Just what I've missed"}
        right={<div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => open({ prefs: "1", ...(dayTitle ? { from: dayTitle } : { missed: "1" }) })}>Preferences</button>
          <button className="btn" onClick={rebuild}>New plan</button>
        </div>} />
      {plan.comeback && <div className="note accent rise">Welcome back: same weights as last time, no extras today. Ease in.</div>}
      {notice && <div className="note" role="status">{notice}</div>}
      {plan.items.length === 0 && <p className="muted">Nothing stands out: every muscle has had its share lately. Pick one of your days instead.</p>}
      <div className="plan-list">
        {main.map((item, i) => <ItemCard key={item.id} item={item} n={`${i + 1}`} onAction={act(item)} />)}
      </div>
      {extra.length > 0 && (
        <section className="plan-extra" aria-label="Extra, if you have time">
          <h2 className="plan-extra-title">Extra, if you have time</h2>
          {extra.map((item) => <ItemCard key={item.id} item={item} n="+" onAction={act(item)} />)}
        </section>
      )}
      <p className="muted" style={{ fontSize: 13, textAlign: "center" }}>Log it in Hevy as usual; it shows on Muscles after your next import.</p>
    </>
  );
}

function PreferencesPanel({ done }: { done: () => void }) {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [muscles, setMuscles] = useState<{ key: string; name: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [musclesFailed, setMusclesFailed] = useState(false);
  useEffect(() => {
    apiFetch<Preferences>("/api/preferences").then(setPrefs).catch((e) => setError(e.message));
    apiFetch<{ key: string; name: string }[]>("/api/muscles").then(setMuscles).catch(() => setMusclesFailed(true));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!prefs) return <p className="muted">Loading…</p>;
  const toggle = (key: string) => setPrefs({ ...prefs, avoid_muscles: prefs.avoid_muscles.includes(key)
    ? prefs.avoid_muscles.filter((k) => k !== key) : [...prefs.avoid_muscles, key] });
  const save = () => {
    setSaving(true);
    apiFetch<Preferences>("/api/preferences", { method: "PUT", body: JSON.stringify(prefs) })
      .then(() => done()).catch((e) => { setError(e.message); setSaving(false); });
  };
  return (
    <>
      <button className="link-btn" onClick={done}>‹ Back</button>
      <PageHeader eyebrow="Planner, focus tips, Muscles and the coach all use these" title="Preferences" />
      <Card i={1}>
        <h2>Leave these muscles out</h2>
        <p className="secondary" style={{ fontSize: 14, marginTop: -4 }}>Never planned or flagged as missing. Exercises that only load them along the way (squats, rows) can still show up.</p>
        {musclesFailed && <p className="error">Couldn't load the muscle list.</p>}
        <div className="chips">
          {muscles.map((m) => (
            <button key={m.key} className={`chip${prefs.avoid_muscles.includes(m.key) ? " left-out" : ""}`}
              aria-pressed={prefs.avoid_muscles.includes(m.key)} onClick={() => toggle(m.key)}>{m.name}</button>
          ))}
        </div>
      </Card>
      <Card i={2}>
        <h2>Never suggest</h2>
        {prefs.never_exercises.length ? prefs.never_exercises.map((name) => (
          <div key={name} className="row spread plan-never">
            <span>{name}</span>
            <button className="btn small ghost" onClick={() => setPrefs({ ...prefs, never_exercises: prefs.never_exercises.filter((n) => n !== name) })}>Allow again</button>
          </div>
        )) : <p className="muted" style={{ margin: 0, fontSize: 14 }}>Nothing yet. Use ⋯ → "Don't suggest this again" on a planned exercise.</p>}
      </Card>
      <Card i={3}>
        <h2>Notes for the coach</h2>
        <label className="field">
          <span className="sr-only">Notes for the coach</span>
          <textarea rows={3} maxLength={1000} value={prefs.coach_notes} placeholder="e.g. Bad lower back from an old injury"
            onChange={(e) => setPrefs({ ...prefs, coach_notes: e.target.value })} />
        </label>
      </Card>
      <div className="row"><button className="btn primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button></div>
    </>
  );
}

export default function Plan() {
  const [params, setParams] = useSearchParams();
  const open = (next: Record<string, string>) => setParams(next);
  if (params.get("prefs") === "1") {
    const from = params.get("from");
    return <PreferencesPanel done={() => setParams(from ? { day: from } : params.get("missed") === "1" ? { missed: "1" } : {})} />;
  }
  const dayTitle = params.get("day");
  if (dayTitle || params.get("missed") === "1") return <PlanView key={dayTitle ?? "missed"} dayTitle={dayTitle} open={open} />;
  return <DayPicker open={open} />;
}
