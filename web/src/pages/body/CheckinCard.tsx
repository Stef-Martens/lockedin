import { type FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../lib/api";
import { type Checkin, parseValue, TIPS } from "../../lib/body";
import { addDays, dayMonthYear, todayLocal } from "../../lib/format";
import { stagger } from "../../lib/motion";
import type { MeasurementType } from "../../lib/types";

const asText = (c: Checkin | undefined): Record<number, string> =>
  c ? Object.fromEntries(Object.entries(c.values).map(([id, v]) => [Number(id), String(v)])) : {};

export default function CheckinCard({ types, checkins, weeks, onSaved }: { types: MeasurementType[]; checkins: Checkin[]; weeks: number; onSaved: () => void }) {
  const [date, setDate] = useState(todayLocal());
  const [values, setValues] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latest = useMemo(() => {
    const out: Record<number, number> = {};
    [...checkins].sort((a, b) => a.measured_on.localeCompare(b.measured_on)).forEach((c) =>
      Object.entries(c.values).forEach(([id, v]) => { out[Number(id)] = v; }));
    return out;
  }, [checkins]);
  const filled = types.filter((t) => parseValue(values[t.id] ?? "") != null).length;
  const existing = checkins.find((c) => c.measured_on === date);
  const pickDate = (d: string) => {
    setDate(d);
    // Editing an earlier check-in: show its values so saving replaces them knowingly
    setValues(asText(checkins.find((c) => c.measured_on === d)));
  };
  // Opening the page on a day you already checked in shows that check-in too (unless you've started typing).
  // Only when the check-ins arrive or change: picking another date is handled by pickDate.
  useEffect(() => {
    const found = checkins.find((c) => c.measured_on === date);
    if (found) setValues((v) => (Object.keys(v).length ? v : asText(found)));
  }, [checkins]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const payload: Record<string, number> = {};
    types.forEach((t) => { const v = parseValue(values[t.id] ?? ""); if (v != null) payload[String(t.id)] = v; });
    if (!Object.keys(payload).length) return;
    setBusy(true);
    try {
      await apiFetch("/api/checkins", { method: "POST", body: JSON.stringify({ measured_on: date, values: payload }) });
      setValues({});
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const last = checkins[0]?.measured_on;
  return (
    <form className="card rise" style={stagger(1)} onSubmit={save}>
      <div className="section-head">
        <h2 style={{ fontSize: 26 }}>Check-in</h2>
        <label className="row checkin-date">Date
          <input type="date" value={date} max={todayLocal()} onChange={(e) => pickDate(e.target.value)} required />
        </label>
      </div>
      {existing ? (
        <p className="note accent" style={{ margin: "-4px 0 12px" }}>You already checked in on {dayMonthYear(date)}. Its values are filled in below; saving replaces them.</p>
      ) : last && <p className="secondary" style={{ margin: "-4px 0 12px", fontSize: 14 }}>Last check-in {dayMonthYear(last)} · next on {dayMonthYear(addDays(last, weeks * 7))}</p>}
      <div className="checkin-grid">
        {types.map((t, n) => {
          const isFilled = parseValue(values[t.id] ?? "") != null;
          return (
            <label key={t.id} className={`field-card rise${isFilled ? " filled" : ""}`} style={stagger(n, 0.1, 0.03)}>
              <span className="row spread" style={{ gap: 8, alignItems: "baseline" }}>
                <span style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>{t.name}</span>
                {latest[t.id] != null && <span className="muted" style={{ fontSize: 12 }}>last {latest[t.id]} {t.unit}</span>}
              </span>
              <span className="row" style={{ gap: 8, alignItems: "baseline", flexWrap: "nowrap" }}>
                <input type="text" inputMode="decimal" value={values[t.id] ?? ""} placeholder="–" aria-label={`${t.name} in ${t.unit}`}
                  onChange={(e) => setValues({ ...values, [t.id]: e.target.value })} className="field-card-input" />
                <span className="muted">{t.unit}</span>
              </span>
              {TIPS[t.name] && <span className="muted" style={{ fontSize: 12, lineHeight: 1.4 }}>{TIPS[t.name]}</span>}
            </label>
          );
        })}
      </div>
      <div className="row spread" style={{ marginTop: 18 }}>
        <div className="row" style={{ gap: 12 }}>
          <div className="checkin-meter">
            <div style={{ width: `${(filled / Math.max(types.length, 1)) * 100}%` }} />
          </div>
          <span className="secondary" style={{ fontSize: 14 }}>{filled} of {types.length} filled</span>
        </div>
        <div className="row" style={{ gap: 14 }}>
          <span className="muted" style={{ fontSize: 13 }}>Blank fields are skipped</span>
          <button className="btn primary" disabled={busy || (!filled && !saved)}>
            {saved ? "Saved" : busy ? "Saving…" : filled ? `Save ${filled} measurement${filled === 1 ? "" : "s"}` : "Save check-in"}
          </button>
        </div>
      </div>
      {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}
    </form>
  );
}
