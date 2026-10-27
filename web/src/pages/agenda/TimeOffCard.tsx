import { useEffect, useState, type FormEvent } from "react";
import { Card, SectionHead } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { emptyForm, entryLine, formBody, formFromEntry, PARTS, type TimeOffEntry, type TimeOffForm, type TimeOffReason } from "../../lib/timeoff";

function Form({ initial, onSaved, onCancel }: { initial: { id: number | null; form: TimeOffForm }; onSaved: () => void; onCancel: () => void }) {
  const [form, setForm] = useState(initial.form);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (patch: Partial<TimeOffForm>) => setForm((f) => ({ ...f, ...patch }));
  const setUntil = (category: keyof TimeOffForm["until"], value: string) => setForm((f) => ({ ...f, until: { ...f.until, [category]: value } }));
  const save = (e: FormEvent) => {
    e.preventDefault();
    const body = formBody(form);
    if (!body) { setError("Pick at least one thing that's off."); return; }
    setSaving(true);
    setError(null);
    apiFetch(initial.id == null ? "/api/time-off" : `/api/time-off/${initial.id}`,
      { method: initial.id == null ? "POST" : "PATCH", body: JSON.stringify(body) })
      .then(onSaved).catch((err) => { setError(err.message); setSaving(false); });
  };
  return (
    <form onSubmit={save} className="stack">
      <div className="timeoff-pair">
        <label className="field">Reason
          <select value={form.reason} onChange={(e) => set({ reason: e.target.value as TimeOffReason })}>
            <option value="vacation">Vacation</option>
            <option value="injury">Injury or operation</option>
          </select>
        </label>
        <label className="field">Label
          <input value={form.label} maxLength={60} placeholder="optional, e.g. Operation" onChange={(e) => set({ label: e.target.value })} />
        </label>
      </div>
      {form.reason === "vacation" ? (
        <div className="timeoff-pair">
          <label className="field">Everything off from
            <input type="date" aria-label="From" required value={form.start} onChange={(e) => set({ start: e.target.value })} />
          </label>
          <label className="field">to
            <input type="date" aria-label="To" value={form.all} onChange={(e) => set({ all: e.target.value })} />
          </label>
        </div>
      ) : (
        <label className="field">Starts
          <input type="date" aria-label="From" required value={form.start} onChange={(e) => set({ start: e.target.value })} />
        </label>
      )}
      <div className="timeoff-parts">
        <div className="muted" style={{ fontSize: 13 }}>{form.reason === "vacation" ? "Or only some things:" : "What's off, and until when:"}</div>
        {PARTS.map((p) => (
          <div key={p.category} className="timeoff-part">
            <select aria-label={p.name} value={form.until[p.category] === "" ? "fine" : "off"}
              onChange={(e) => setUntil(p.category, e.target.value === "off" ? form.start : "")}>
              <option value="fine">{p.name}: fine</option>
              <option value="off">{p.name}: off until</option>
            </select>
            {form.until[p.category] !== "" && (
              <input type="date" aria-label={`${p.name} until`} value={form.until[p.category]} onChange={(e) => setUntil(p.category, e.target.value)} />
            )}
          </div>
        ))}
      </div>
      {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div className="row">
        <button className="btn primary" type="submit" disabled={saving}>Save</button>
        <button className="btn ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** Vacations and injuries or operations that are under way or coming, to add, change or remove. */
export default function TimeOffCard({ onChange }: { onChange: () => void }) {
  const [entries, setEntries] = useState<TimeOffEntry[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: number | null; form: TimeOffForm } | null>(null);
  const [confirm, setConfirm] = useState<number | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let current = true;
    apiFetch<TimeOffEntry[]>("/api/time-off").then((e) => { if (current) setEntries(e); })
      .catch(() => { if (current) setFailed("Couldn't load your time off."); });
    return () => { current = false; };
  }, [reloads]);

  const changed = () => { setEditing(null); setConfirm(null); setReloads((n) => n + 1); onChange(); };
  const remove = (id: number) => apiFetch(`/api/time-off/${id}`, { method: "DELETE" }).then(changed).catch((e) => { setConfirm(null); setFailed(e.message); });

  return (
    <Card i={0} className="timeoff-card">
      <SectionHead title="Time off" right={!editing && <button className="btn small" onClick={() => setEditing({ id: null, form: emptyForm() })}>Add time off</button>} />
      {editing ? (
        <Form initial={editing} onSaved={changed} onCancel={() => setEditing(null)} />
      ) : (
        <>
          {failed && <p className="error" role="alert" style={{ margin: 0 }}>{failed}</p>}
          {entries && entries.length === 0 && !failed && (
            <p className="muted flush" style={{ fontSize: 14 }}>No time off planned. Add a vacation or an operation and the plans, streak and forecasts work around it, or just tell the coach.</p>
          )}
          <ul className="list">
            {(entries ?? []).map((e) => (
              <li key={e.id} className="timeoff-row">
                <span>{entryLine(e)}</span>
                <span className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                  <button className="btn small ghost" onClick={() => setEditing({ id: e.id, form: formFromEntry(e) })}>Edit</button>
                  {confirm === e.id ? <button className="btn small danger" onClick={() => remove(e.id)}>Yes, delete it</button>
                    : <button className="btn small ghost" onClick={() => setConfirm(e.id)}>Delete</button>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
