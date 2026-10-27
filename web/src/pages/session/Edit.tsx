import { useState, type FormEvent } from "react";
import { Card } from "../../components/ui";
import type { AgendaItem } from "../../lib/agenda";
import { apiFetch } from "../../lib/api";
import { formatDuration } from "../../lib/format";

/** Change a planned session: title, day, note, and for runs and swims the targets. */
export default function Edit({ item, onSaved, onCancel }: { item: AgendaItem; onSaved: () => void; onCancel: () => void }) {
  const t = item.targets ?? {};
  const toClock = (s?: number) => (s ? formatDuration(s) : "");
  const fromClock = (v: string) => { const [m, s] = v.split(":").map(Number); return v ? m * 60 + (s || 0) : undefined; };
  // Phones with a Dutch/Belgian keyboard type "8,5".
  const num = (v: string) => Number(v.replace(",", "."));
  const sameTargets = (a: object, b: object) => {
    const norm = (o: object) => JSON.stringify(Object.entries(o).filter(([, v]) => v != null).sort(([x], [y]) => x.localeCompare(y)));
    return norm(a) === norm(b);
  };
  const [form, setForm] = useState({
    title: item.title, note: item.note ?? "", day: item.day, optional: item.optional,
    distance: t.distance_m ? String(t.distance_m / 1000) : "", duration: t.duration_s ? String(Math.round(t.duration_s / 60)) : "",
    low: toClock(t.pace_low), high: toClock(t.pace_high), zone: t.hr_zone ? String(t.hr_zone) : "",
  });
  const [error, setError] = useState<string | null>(null);
  const withTargets = item.sport === "run" || item.sport === "swim";
  const save = (e: FormEvent) => {
    e.preventDefault();
    const changes: Record<string, unknown> = {};
    if (form.title !== item.title) changes.title = form.title;
    if (form.note !== (item.note ?? "")) changes.note = form.note || null;
    if (form.day !== item.day) changes.day = form.day;
    if (form.optional !== item.optional) changes.optional = form.optional;
    if (withTargets) {
      const values = [form.distance, form.duration].filter(Boolean).map(num);
      const clocks = [form.low, form.high].filter(Boolean);
      if (values.some((v) => !Number.isFinite(v)) || clocks.some((c) => !/^\d{1,2}:\d{2}$/.test(c.trim()))) {
        setError("Use numbers for distance and minutes, and m:ss for paces (e.g. 5:35).");
        return;
      }
      const next = {
        distance_m: form.distance ? Math.round(num(form.distance) * 1000) : undefined,
        duration_s: form.duration ? (t.duration_s && Math.round(t.duration_s / 60) === num(form.duration) ? t.duration_s : Math.round(num(form.duration) * 60)) : undefined,
        pace_low: fromClock(form.low), pace_high: fromClock(form.high),
        hr_zone: form.zone && item.sport === "run" ? Number(form.zone) : undefined,
      };
      const clean = Object.fromEntries(Object.entries(next).filter(([, v]) => v !== undefined));
      if (!sameTargets(clean, t)) {
        changes.targets = Object.keys(clean).length ? clean : null;
      }
    }
    if (!Object.keys(changes).length) return onCancel();
    apiFetch(`/api/agenda/${item.id}`, { method: "PATCH", body: JSON.stringify(changes) }).then(onSaved).catch((err) => setError(err.message));
  };
  const unit = item.sport === "run" ? "per km" : "per 100 m";
  return (
    <Card i={1}>
      <form onSubmit={save} className="stack">
        <label className="field">Title<input value={form.title} maxLength={80} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="field">Day<input type="date" value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} /></label>
        <label className="field">Note<textarea rows={2} maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
        {withTargets && (
          <div className="grid-form">
            <label className="field">Distance (km)<input inputMode="decimal" value={form.distance} onChange={(e) => setForm({ ...form, distance: e.target.value })} /></label>
            <label className="field">Duration (min)<input inputMode="numeric" value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} /></label>
            <label className="field">Pace from ({unit})<input placeholder="5:35" value={form.low} onChange={(e) => setForm({ ...form, low: e.target.value })} /></label>
            <label className="field">Pace to ({unit})<input placeholder="5:50" value={form.high} onChange={(e) => setForm({ ...form, high: e.target.value })} /></label>
            {item.sport === "run" && (
              <label className="field">Heart-rate zone
                <select value={form.zone} onChange={(e) => setForm({ ...form, zone: e.target.value })}>
                  <option value="">None</option>{[1, 2, 3, 4, 5].map((z) => <option key={z} value={z}>Zone {z}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
        <label className="row check-row">
          <input type="checkbox" checked={form.optional} onChange={(e) => setForm({ ...form, optional: e.target.checked })} /> Optional
        </label>
        {error && <p className="error flush" role="alert">{error}</p>}
        <div className="row"><button className="btn primary" type="submit">Save</button><button className="btn" type="button" onClick={onCancel}>Cancel</button></div>
      </form>
    </Card>
  );
}
