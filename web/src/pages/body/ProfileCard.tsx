import { type FormEvent, useEffect, useState } from "react";
import { SectionHead } from "../../components/ui";
import { stagger } from "../../lib/motion";
import type { Profile } from "../../lib/types";

const toNum = (v: string) => (v === "" ? null : Number(v));

export default function ProfileCard({ profile, ready, onSave }: { profile: Profile; ready: boolean; onSave: (p: Partial<Profile>) => Promise<void> }) {
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
      // The reminder card saves its own fields; leaving them out here can't undo its changes.
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
      <fieldset disabled={!ready} className="plain">
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
