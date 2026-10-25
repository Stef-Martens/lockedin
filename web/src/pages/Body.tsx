import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Card, PageHeader, SectionHead, Segmented } from "../components/ui";
import { apiDownload, apiFetch } from "../lib/api";
import { type Checkin, historyRows, parseValue, TIPS } from "../lib/body";
import { todayLocal } from "../lib/format";
import { stagger } from "../lib/motion";
import type { MeasurementType, Profile } from "../lib/types";

const EMPTY: Profile = { date_of_birth: null, height_cm: null, sex: null, max_hr_override: null, ftp_override: null,
  resting_hr_override: null, dumbbell_weights: "pair", reminder_weeks: 2, reminder_hevy: true };
const toNum = (v: string) => (v === "" ? null : Number(v));
const fmtDate = (d: string, year = true) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", ...(year ? { year: "numeric" } : {}), timeZone: "UTC" });
const addDays = (d: string, n: number) => new Date(new Date(`${d}T12:00:00Z`).getTime() + n * 864e5).toISOString().slice(0, 10);

function CheckinCard({ types, checkins, weeks, onSaved }: { types: MeasurementType[]; checkins: Checkin[]; weeks: number; onSaved: () => void }) {
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
  const asText = (c: Checkin | undefined) =>
    c ? Object.fromEntries(Object.entries(c.values).map(([id, v]) => [Number(id), String(v)])) : {};
  const pickDate = (d: string) => {
    setDate(d);
    // Editing an earlier check-in: show its values so saving replaces them knowingly
    setValues(asText(checkins.find((c) => c.measured_on === d)));
  };
  // Opening the page on a day you already checked in shows that check-in too (unless you've started typing)
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
        <label className="row" style={{ gap: 10, fontSize: 14, color: "var(--ink-3)" }}>Date
          <input type="date" value={date} max={todayLocal()} onChange={(e) => pickDate(e.target.value)} required
            style={{ background: "var(--sunken)", border: "1px solid var(--axis)", borderRadius: 10, padding: "9px 10px", colorScheme: "dark" }} />
        </label>
      </div>
      {existing ? (
        <p className="note accent" style={{ margin: "-4px 0 12px" }}>You already checked in on {fmtDate(date)}. Its values are filled in below; saving replaces them.</p>
      ) : last && <p className="secondary" style={{ margin: "-4px 0 12px", fontSize: 14 }}>Last check-in {fmtDate(last)} · next on {fmtDate(addDays(last, weeks * 7))}</p>}
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
          <div style={{ width: 160, height: 6, background: "var(--hairline)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${(filled / Math.max(types.length, 1)) * 100}%`, background: "var(--accent)", borderRadius: 3, transition: "width .25s ease" }} />
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

function History({ types, checkins, onDeleted }: { types: MeasurementType[]; checkins: Checkin[]; onDeleted: () => void }) {
  const [error, setError] = useState<string | null>(null);
  async function remove(d: string) {
    if (!window.confirm(`Delete the check-in of ${fmtDate(d)}?`)) return;
    setError(null);
    try {
      await apiFetch(`/api/checkins/${d}`, { method: "DELETE" });
      onDeleted();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const ids = types.map((t) => t.id);
  const rows = historyRows(checkins, ids);
  if (!rows.length) return null;
  return (
    <Card i={2} className="pop">
      <SectionHead title="History" right={<span className="muted" style={{ fontSize: 13 }}>Change vs the previous check-in</span>} />
      <div className="table-wrap">
        <table className="table num" style={{ minWidth: 200 + types.length * 92 }}>
          <thead>
            <tr><th>Date</th>{types.map((t) => <th key={t.id} className="num">{t.name}</th>)}<th><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.measured_on}>
                <td className="secondary">{fmtDate(r.measured_on)}</td>
                {r.cells.map((c, n) => (
                  <td key={n} className="num">
                    <span className="display" style={{ fontSize: 20, fontWeight: 700 }}>{c.value ?? "–"}</span>
                    {c.delta != null && <span style={{ display: "block", fontSize: 12, color: "var(--ink-3)" }}>{c.delta === 0 ? "±0" : `${c.delta > 0 ? "+" : "−"}${Math.abs(c.delta).toFixed(1)}`}</span>}
                  </td>
                ))}
                <td className="num"><button className="btn ghost" onClick={() => remove(r.measured_on)} aria-label={`Delete check-in of ${fmtDate(r.measured_on)}`}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}
    </Card>
  );
}

function ReminderCard({ profile, ready }: { profile: Profile; ready: boolean }) {
  const [weeks, setWeeks] = useState(profile.reminder_weeks);
  const [hevy, setHevy] = useState(profile.reminder_hevy);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);
  useEffect(() => { setWeeks(profile.reminder_weeks); setHevy(profile.reminder_hevy); }, [profile.reminder_weeks, profile.reminder_hevy]);
  const every = weeks === 1 ? "week" : `${weeks} weeks`;

  // Only the reminder fields go to the server, so nothing else in the profile can be overwritten.
  async function save(change: Partial<Pick<Profile, "reminder_weeks" | "reminder_hevy">>, undo: () => void) {
    setNote(null);
    try {
      await apiFetch("/api/profile", { method: "PATCH", body: JSON.stringify(change) });
      setNote({ text: "Saved. Add the calendar event again so it uses the new setting (and remove the old one).", ok: true });
    } catch (e) {
      undo();
      setNote({ text: (e as Error).message, ok: false });
    }
  }
  async function download() {
    setNote(null);
    try {
      const how = await apiDownload("/api/reminders/calendar.ics", "lockedin-checkin.ics", "text/calendar");
      setNote({ ok: true, text: how === "shared"
        ? "Choose Calendar in the share sheet to add the reminder."
        : `Downloaded. Open lockedin-checkin.ics to add a reminder every ${every}${hevy ? ", with the Hevy upload" : ""}.` });
    } catch (e) {
      if ((e as Error).name !== "AbortError") setNote({ text: (e as Error).message, ok: false });
    }
  }
  return (
    <Card i={4}>
      <SectionHead title="Reminder" />
      <p className="secondary" style={{ marginTop: -4, fontSize: 14, lineHeight: 1.5 }}>Your calendar reminds you; the event opens this check-in.</p>
      <fieldset disabled={!ready} style={{ border: 0, padding: 0, margin: 0 }}>
        <Segmented label="Remind me every" value={weeks} onChange={(w) => { const prev = weeks; setWeeks(w); save({ reminder_weeks: w }, () => setWeeks(prev)); }}
          options={[{ value: 1, label: "Every week" }, { value: 2, label: "Every 2 weeks" }, { value: 4, label: "Every 4 weeks" }]} />
        <label className="row" style={{ gap: 10, marginTop: 14, fontSize: 14, color: "var(--ink-2)", cursor: "pointer" }}>
          <input type="checkbox" checked={hevy} onChange={(e) => { const v = e.target.checked; setHevy(v); save({ reminder_hevy: v }, () => setHevy(!v)); }}
            style={{ width: 18, height: 18, accentColor: "var(--accent)" }} />
          Also remind me to upload my Hevy export
        </label>
        <div className="row" style={{ marginTop: 16 }}>
          <button type="button" className="btn primary" onClick={download}>Add to calendar</button>
          <span style={{ fontSize: 13, color: note ? (note.ok ? "var(--accent)" : "var(--danger)") : "var(--ink-muted)" }}>
            {note?.text ?? "Adds a repeating event to iPhone or Mac Calendar."}
          </span>
        </div>
      </fieldset>
    </Card>
  );
}

function ProfileCard({ profile, ready, onSave }: { profile: Profile; ready: boolean; onSave: (p: Partial<Profile>) => Promise<void> }) {
  const [p, setP] = useState<Profile>(profile);
  const [dirty, setDirty] = useState(false);
  // What's typed in the number fields, kept as text so "182," or "182." can be typed on the way to 182.5
  const [raw, setRaw] = useState<Partial<Record<keyof Profile, string>>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Fresh server data only replaces the form while you haven't started editing it
  useEffect(() => { if (!dirty) { setP(profile); setRaw({}); } }, [profile, dirty]);
  const edit = (next: Profile) => { setDirty(true); setP(next); };

  async function save(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setError(null);
    try {
      const { reminder_weeks: _w, reminder_hevy: _h, ...fields } = p;
      await onSave(fields);
      setRaw({});
      setDirty(false);
      setMsg("Saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }
  const num = (k: keyof Profile, label: string, hint?: string, accent = false) => (
    <label className="field">{label}
      <input type="text" inputMode="decimal" value={raw[k] ?? String((p[k] as number | null) ?? "")} placeholder={hint} className={accent ? "accent" : ""}
        onChange={(e) => { setRaw({ ...raw, [k]: e.target.value }); edit({ ...p, [k]: toNum(e.target.value.trim().replace(",", ".")) }); }} />
    </label>
  );
  return (
    <form className="card rise" style={stagger(3)} onSubmit={save}>
      <SectionHead title="Profile" />
      <fieldset disabled={!ready} style={{ border: 0, padding: 0, margin: 0 }}>
      <div className="grid-form" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
        <label className="field">Date of birth
          <input type="date" value={p.date_of_birth ?? ""} onChange={(e) => edit({ ...p, date_of_birth: e.target.value || null })} />
        </label>
        {num("height_cm", "Height (cm)", "cm")}
        {num("ftp_override", "FTP (W)", "estimated from rides", !p.ftp_override)}
        {num("max_hr_override", "Max heart rate", "from your rides")}
        {num("resting_hr_override", "Resting heart rate", "optional")}
        <label className="field">Dumbbell weights in Hevy
          <select value={p.dumbbell_weights} onChange={(e) => edit({ ...p, dumbbell_weights: e.target.value as Profile["dumbbell_weights"] })}>
            <option value="pair">Total of both dumbbells</option>
            <option value="each">Per dumbbell</option>
          </select>
        </label>
      </div>
      <p className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>Zwift shows your FTP in your profile. Entering it makes effort labels and ride suggestions accurate; every ride's TSS is recalculated.</p>
      <div className="row">
        <button className="btn primary">Save profile</button>
        {msg && <span className="ok">{msg}</span>}
        {error && <span className="error">{error}</span>}
      </div>
      </fieldset>
    </form>
  );
}

function GuideCard({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("cm");
  const [error, setError] = useState<string | null>(null);
  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/measurement-types", { method: "POST", body: JSON.stringify({ name, unit, kind: unit === "kg" ? "weight" : "tape" }) });
      setName("");
      onAdded();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Card i={5}>
      <SectionHead title="Measure the same way every time" />
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, color: "var(--ink-2)", lineHeight: 1.7 }}>
        <li>Morning, before eating or training; weight after the toilet.</li>
        <li>Tape snug on the skin, not pulling it in; read it in a mirror.</li>
        <li>Relaxed muscles, unless you always measure flexed. Pick one and stick to it.</li>
        <li>Small swings (±0.5 cm, ±1 kg) are normal day-to-day noise.</li>
      </ul>
      <form onSubmit={add} className="row" style={{ marginTop: 16, alignItems: "flex-end" }}>
        <label className="field" style={{ flex: "1 1 160px" }}>Track something else
          <input value={name} placeholder="e.g. Calves" onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="field" style={{ width: 90 }}>Unit
          <select value={unit} onChange={(e) => setUnit(e.target.value)}><option>cm</option><option>kg</option><option>%</option></select>
        </label>
        <button className="btn">Add</button>
      </form>
      {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}
    </Card>
  );
}

export default function Body() {
  const [types, setTypes] = useState<MeasurementType[]>([]);
  const [checkins, setCheckins] = useState<Checkin[]>([]);
  const [profile, setProfile] = useState<Profile>(EMPTY);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [t, c, p] = await Promise.all([
        apiFetch<MeasurementType[]>("/api/measurement-types"),
        apiFetch<Checkin[]>("/api/checkins"),
        apiFetch<Profile>("/api/profile"),
      ]);
      setTypes(t);
      setCheckins(c);
      setProfile(p);
      setReady(true);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  useEffect(() => { load(); }, []);

  const saveProfile = async (change: Partial<Profile>) =>
    setProfile(await apiFetch<Profile>("/api/profile", { method: "PATCH", body: JSON.stringify(change) }));
  const every = profile.reminder_weeks === 1 ? "week" : `${profile.reminder_weeks} weeks`;

  return (
    <>
      <PageHeader title="Body" sub={`A check-in every ${every}. Same time of day, before training.`} />
      {error && (
        <div className="note row spread"><span className="error">Couldn't load your body data: {error}</span><button className="btn" onClick={load}>Try again</button></div>
      )}
      <CheckinCard types={types} checkins={checkins} weeks={profile.reminder_weeks} onSaved={load} />
      <History types={types} checkins={checkins} onDeleted={load} />
      <div className="grid-auto" style={{ ["--min" as string]: "420px" }}>
        <ProfileCard profile={profile} ready={ready} onSave={saveProfile} />
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <ReminderCard profile={profile} ready={ready} />
          <GuideCard onAdded={load} />
        </div>
      </div>
    </>
  );
}
