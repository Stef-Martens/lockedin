import { type FormEvent, useEffect, useMemo, useState } from "react";
import SeriesChart from "../components/SeriesChart";
import { apiFetch } from "../lib/api";
import { todayLocal } from "../lib/format";
import type { Measurement, MeasurementType, Profile } from "../lib/types";

const EMPTY: Profile = { date_of_birth: null, height_cm: null, sex: null, max_hr_override: null, ftp_override: null, resting_hr_override: null };
const toNum = (v: string) => (v === "" ? null : Number(v));
const dayMs = (d: string) => new Date(`${d}T12:00:00Z`).getTime();
const shortDate = (ms: number) => new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Europe/Brussels" });

function ProfileForm() {
  const [p, setP] = useState<Profile>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { apiFetch<Profile>("/api/profile").then(setP); }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setError(null);
    try {
      setP(await apiFetch<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(p) }));
      setMsg("Saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const num = (k: keyof Profile, label: string, hint?: string) => (
    <label className="field">
      {label}
      <input type="number" inputMode="decimal" value={(p[k] as number | null) ?? ""} placeholder={hint}
        onChange={(e) => setP({ ...p, [k]: toNum(e.target.value) })} />
    </label>
  );

  return (
    <form className="card" onSubmit={save}>
      <h2>Profile</h2>
      <div className="grid-form">
        <label className="field">
          Date of birth
          <input type="date" value={p.date_of_birth ?? ""} onChange={(e) => setP({ ...p, date_of_birth: e.target.value || null })} />
        </label>
        {num("height_cm", "Height (cm)")}
        <label className="field">
          Sex
          <select value={p.sex ?? ""} onChange={(e) => setP({ ...p, sex: (e.target.value || null) as Profile["sex"] })}>
            <option value="">–</option>
            <option value="male">Male</option>
            <option value="female">Female</option>
          </select>
        </label>
        {num("max_hr_override", "Max heart rate", "auto")}
        {num("resting_hr_override", "Resting heart rate", "optional")}
        {num("ftp_override", "FTP (W)", "auto")}
      </div>
      <p className="muted" style={{ fontSize: "0.85rem" }}>Leave max heart rate and FTP empty and they're estimated from your rides.</p>
      <div className="row">
        <button className="btn primary">Save profile</button>
        {msg && <span className="ok">{msg}</span>}
        {error && <span className="error">{error}</span>}
      </div>
    </form>
  );
}

export default function Body() {
  const [types, setTypes] = useState<MeasurementType[]>([]);
  const [rows, setRows] = useState<Measurement[]>([]);
  const [typeId, setTypeId] = useState<number | "">("");
  const [date, setDate] = useState(todayLocal());
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [newType, setNewType] = useState({ name: "", unit: "cm" });

  const load = async () => {
    const [t, m] = await Promise.all([
      apiFetch<MeasurementType[]>("/api/measurement-types"),
      apiFetch<Measurement[]>("/api/measurements"),
    ]);
    setTypes(t);
    setRows(m);
    setTypeId((cur) => cur || t[0]?.id || "");
  };
  useEffect(() => { load(); }, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/measurements", { method: "POST", body: JSON.stringify({ type_id: typeId, measured_on: date, value: Number(value) }) });
      setValue("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addType(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const t = await apiFetch<MeasurementType>("/api/measurement-types", {
        method: "POST", body: JSON.stringify({ ...newType, kind: newType.unit === "kg" ? "weight" : "tape" }),
      });
      setNewType({ name: "", unit: "cm" });
      await load();
      setTypeId(t.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(id: number) {
    await apiFetch(`/api/measurements/${id}`, { method: "DELETE" });
    await load();
  }

  const byType = useMemo(() => {
    const m = new Map<number, Measurement[]>();
    rows.forEach((r) => m.set(r.type_id, [...(m.get(r.type_id) ?? []), r]));
    return m;
  }, [rows]);
  const unit = types.find((t) => t.id === typeId)?.unit ?? "";
  const recent = [...rows].sort((a, b) => b.measured_on.localeCompare(a.measured_on) || b.id - a.id).slice(0, 8);

  return (
    <>
      <h1>Body</h1>
      <p className="secondary">Log a measurement every few weeks to see how you're changing.</p>

      <form className="card" onSubmit={add}>
        <h2>Add a measurement</h2>
        <div className="grid-form">
          <label className="field">
            What
            <select value={typeId} onChange={(e) => setTypeId(Number(e.target.value))}>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <label className="field">
            Date
            <input type="date" value={date} max={todayLocal()} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="field">
            Value ({unit})
            <input type="number" inputMode="decimal" step="0.1" min="0.1" value={value} onChange={(e) => setValue(e.target.value)} required />
          </label>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={!typeId}>Add</button>
          {error && <span className="error">{error}</span>}
        </div>
      </form>

      {types.filter((t) => (byType.get(t.id)?.length ?? 0) > 0).map((t) => {
        const data = byType.get(t.id)!;
        const last = data[data.length - 1];
        const first = data[0];
        const change = data.length > 1 ? last.value - first.value : null;
        return (
          <SeriesChart key={t.id} title={t.name} height={150}
            summary={`${last.value} ${t.unit}${change != null ? ` (${change >= 0 ? "+" : "−"}${Math.abs(change).toFixed(1)} since ${shortDate(dayMs(first.measured_on))})` : ""}`}
            points={data.map((m) => ({ x: dayMs(m.measured_on), y: m.value }))} colorVar="--series-body"
            formatX={shortDate} formatY={(y) => `${y.toFixed(1)} ${t.unit}`} formatTick={(y) => y.toFixed(1)} />
        );
      })}

      {recent.length > 0 && (
        <section className="card">
          <h2>Recent entries</h2>
          <table className="table num">
            <tbody>
              {recent.map((r) => {
                const t = types.find((x) => x.id === r.type_id);
                return (
                  <tr key={r.id}>
                    <td>{shortDate(dayMs(r.measured_on))}</td>
                    <td>{t?.name}</td>
                    <td className="num">{r.value} {t?.unit}</td>
                    <td className="num"><button className="btn ghost" onClick={() => remove(r.id)} aria-label={`Delete ${t?.name} on ${r.measured_on}`}>Delete</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      <form className="card" onSubmit={addType}>
        <h2>Track something else</h2>
        <div className="grid-form">
          <label className="field">
            Name
            <input value={newType.name} placeholder="e.g. Calves" onChange={(e) => setNewType({ ...newType, name: e.target.value })} required />
          </label>
          <label className="field">
            Unit
            <select value={newType.unit} onChange={(e) => setNewType({ ...newType, unit: e.target.value })}>
              <option value="cm">cm</option>
              <option value="kg">kg</option>
              <option value="%">%</option>
            </select>
          </label>
        </div>
        <button className="btn" style={{ marginTop: 12 }}>Add measurement type</button>
      </form>

      <ProfileForm />
    </>
  );
}
