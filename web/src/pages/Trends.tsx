import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import MuscleCoverage from "../components/MuscleCoverage";
import SeriesChart, { type Point } from "../components/SeriesChart";
import WeeklyBars from "../components/WeeklyBars";
import { apiFetch } from "../lib/api";
import type { Coverage, EffortMix, FocusItem } from "../lib/focus";
import { formatPace, formatSwimPace } from "../lib/format";

type Tab = "bike" | "run" | "swim" | "gym";
const TABS: { key: Tab; label: string }[] = [
  { key: "bike", label: "Bike" }, { key: "run", label: "Run" }, { key: "swim", label: "Swim" }, { key: "gym", label: "Gym" },
];
type GymItem = Extract<FocusItem, { type: "gym" }>;
type SessionItem = Extract<FocusItem, { type: "session" }>;

const dayMs = (d: string) => new Date(`${d}T12:00:00Z`).getTime();
const shortDate = (ms: number) => new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Europe/Brussels" });
function pts<T>(rows: T[], date: (r: T) => string, y: (r: T) => number | null | undefined): Point[] {
  return rows.filter((r) => y(r) != null).map((r) => ({ x: dayMs(date(r)), y: y(r) as number }));
}

function Empty({ what }: { what: string }) {
  return (
    <section className="card">
      <p style={{ margin: 0 }}>No {what} yet.</p>
      <p className="secondary" style={{ marginBottom: 0 }}>They show up here once they sync, or <Link to="/import">import them yourself</Link>.</p>
    </section>
  );
}

function Mix({ mix }: { mix: EffortMix }) {
  const total = Object.values(mix.counts).reduce((a, b) => a + b, 0);
  if (!total) return null;
  return (
    <section className="card">
      <h2>Last 4 weeks by effort</h2>
      <div className="tiles" style={{ marginBottom: 0 }}>
        {(["easy", "steady", "hard", "long"] as const).map((k) => (
          <div className="tile" key={k}><div className="label">{k}</div><div className="value num">{mix.counts[k]}</div></div>
        ))}
      </div>
    </section>
  );
}

function Suggestion({ items, sport }: { items: SessionItem[]; sport: string }) {
  const mine = items.filter((s) => s.sport === sport);
  if (!mine.length) return null;
  return (
    <section className="card note-card">
      <h2>Try this</h2>
      {mine.map((s, i) => (
        <p key={i} style={{ margin: "4px 0" }}><strong>{s.title}</strong>: {s.detail} <span className="muted">({s.reason.toLowerCase()})</span></p>
      ))}
    </section>
  );
}

function useFocusSessions(): SessionItem[] {
  const [items, setItems] = useState<SessionItem[]>([]);
  useEffect(() => {
    apiFetch<{ session_suggestions: Omit<SessionItem, "type">[] }>("/api/focus")
      .then((f) => setItems(f.session_suggestions.map((s) => ({ type: "session" as const, ...s })))).catch(() => undefined);
  }, []);
  return items;
}

interface BikeData { rides: { date: string; np: number | null; efficiency: number | null; best_20m: number | null }[];
  weekly: { week_start: string; minutes: number; tss: number }[]; ftp: number | null; mix: EffortMix }
function Bike() {
  const [d, setD] = useState<BikeData | null>(null);
  const sugg = useFocusSessions();
  useEffect(() => { apiFetch<BikeData>("/api/trends/bike").then(setD); }, []);
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.rides.length) return <Empty what="rides" />;
  return (
    <>
      <div className="tiles">
        <div className="tile"><div className="label">FTP (estimate)</div><div className="value num">{d.ftp ? `${Math.round(d.ftp)} W` : "–"}</div></div>
        <div className="tile"><div className="label">Rides (26 wk)</div><div className="value num">{d.rides.length}</div></div>
      </div>
      <Suggestion items={sugg} sport="bike" />
      <SeriesChart title="Normalized power per ride" points={pts(d.rides, (r) => r.date, (r) => r.np)} colorVar="--series-power"
        formatX={shortDate} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} />
      <SeriesChart title="Efficiency (power ÷ heart rate)" summary="higher = fitter" points={pts(d.rides, (r) => r.date, (r) => r.efficiency)}
        colorVar="--series-cadence" formatX={shortDate} formatY={(y) => y.toFixed(2)} />
      <SeriesChart title="Best 20-min power" points={pts(d.rides, (r) => r.date, (r) => r.best_20m)} colorVar="--series-power"
        formatX={shortDate} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} />
      <Mix mix={d.mix} />
    </>
  );
}

interface RunData { runs: { date: string; pace_s_per_km: number | null; aerobic_efficiency: number | null }[];
  weekly: { week_start: string; km: number }[]; mix: EffortMix }
function Run() {
  const [d, setD] = useState<RunData | null>(null);
  const sugg = useFocusSessions();
  useEffect(() => { apiFetch<RunData>("/api/trends/run").then(setD); }, []);
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.runs.length) return <Empty what="runs" />;
  return (
    <>
      <Suggestion items={sugg} sport="run" />
      <SeriesChart title="Pace per run" points={pts(d.runs, (r) => r.date, (r) => r.pace_s_per_km)} colorVar="--series-pace" reversed
        formatX={shortDate} formatY={(y) => formatPace(y)} formatTick={(y) => formatPace(y).replace(" /km", "")} />
      <SeriesChart title="Aerobic efficiency" summary="higher = fitter" points={pts(d.runs, (r) => r.date, (r) => r.aerobic_efficiency)}
        colorVar="--series-cadence" formatX={shortDate} formatY={(y) => y.toFixed(2)} />
      <WeeklyBars title="Weekly distance" rows={d.weekly} dataKey="km" colorVar="--sport-run" format={(v) => `${v} km`} />
      <Mix mix={d.mix} />
    </>
  );
}

interface SwimData { swims: { date: string; pace_s_per_100m: number | null }[]; weekly: { week_start: string; m: number }[] }
function Swim() {
  const [d, setD] = useState<SwimData | null>(null);
  useEffect(() => { apiFetch<SwimData>("/api/trends/swim").then(setD); }, []);
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.swims.length) return <Empty what="swims" />;
  return (
    <>
      <WeeklyBars title="Weekly distance" rows={d.weekly} dataKey="m" colorVar="--sport-swim" format={(v) => `${v} m`} />
      <SeriesChart title="Pace per 100 m" points={pts(d.swims, (r) => r.date, (r) => r.pace_s_per_100m)} colorVar="--sport-swim" reversed
        formatX={shortDate} formatY={(y) => formatSwimPace(y)} formatTick={(y) => formatSwimPace(y).replace(" /100m", "")} />
    </>
  );
}

interface Exercise { id: number; name: string; sessions: number; last_done: string; best_e1rm: number | null; mapped: boolean }
interface Muscle { key: string; name: string; region: string }
interface Progress { exercise: string; sessions: { date: string; best_e1rm: number }[] }

function TagForm({ exercise, muscles, onSaved }: { exercise: Exercise; muscles: Muscle[]; onSaved: () => void }) {
  const [equipment, setEquipment] = useState("machine");
  const [primary, setPrimary] = useState<string[]>([]);
  const [secondary, setSecondary] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await apiFetch(`/api/gym/exercises/${exercise.id}/muscles`, { method: "PUT", body: JSON.stringify({ equipment, primary, secondary }) });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  const pick = (setter: (v: string[]) => void) => (e: React.ChangeEvent<HTMLSelectElement>) =>
    setter(Array.from(e.target.selectedOptions).map((o) => o.value));
  return (
    <form onSubmit={save} className="tag-form">
      <div className="list-title">{exercise.name}</div>
      <div className="grid-form">
        <label className="field">Equipment
          <select value={equipment} onChange={(e) => setEquipment(e.target.value)}>
            {["barbell", "dumbbell", "cable", "machine", "bodyweight", "other"].map((x) => <option key={x}>{x}</option>)}
          </select>
        </label>
        <label className="field">Main muscles
          <select multiple size={5} value={primary} onChange={pick(setPrimary)} required>
            {muscles.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}
          </select>
        </label>
        <label className="field">Helping muscles
          <select multiple size={5} value={secondary} onChange={pick(setSecondary)}>
            {muscles.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}
          </select>
        </label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn primary" disabled={!primary.length}>Save</button>
        {error && <span className="error">{error}</span>}
      </div>
    </form>
  );
}

function Gym() {
  const [cov, setCov] = useState<{ coverage: Coverage[]; unmapped: string[] } | null>(null);
  const [sugg, setSugg] = useState<GymItem[]>([]);
  const [volume, setVolume] = useState<{ week_start: string; volume_kg: number }[]>([]);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [muscles, setMuscles] = useState<Muscle[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);

  const load = () => {
    apiFetch<{ coverage: Coverage[]; unmapped: string[] }>("/api/gym/coverage").then(setCov);
    apiFetch<Omit<GymItem, "type">[]>("/api/gym/suggestions?limit=20").then((s) => setSugg(s.map((x) => ({ type: "gym" as const, ...x }))));
    apiFetch<typeof volume>("/api/gym/volume?weeks=26").then(setVolume);
    apiFetch<Exercise[]>("/api/gym/exercises").then(setExercises);
  };
  useEffect(() => {
    load();
    apiFetch<Muscle[]>("/api/muscles").then(setMuscles);
  }, []);
  useEffect(() => {
    setProgress(null);
    if (open != null) apiFetch<Progress>(`/api/gym/exercises/${open}`).then(setProgress);
  }, [open]);

  if (!cov) return <p className="muted">Loading…</p>;
  if (!exercises.length) return <Empty what="gym workouts" />;
  const unmapped = exercises.filter((e) => !e.mapped);
  return (
    <>
      {cov.coverage.length ? <MuscleCoverage coverage={cov.coverage} suggestions={sugg} />
        : <section className="card"><p style={{ margin: 0 }}>No gym sessions in the last 4 weeks.</p></section>}
      <WeeklyBars title="Weekly volume" summary="kg × reps" rows={volume} dataKey="volume_kg" colorVar="--sport-gym"
        format={(v) => `${Math.round(v).toLocaleString("en-GB")} kg`} />
      <section className="card" style={{ padding: 4 }}>
        <h2 style={{ padding: "12px 12px 0" }}>Exercises</h2>
        <ul className="list">
          {exercises.map((e) => (
            <li key={e.id}>
              <button className="list-item exercise-row" onClick={() => setOpen(open === e.id ? null : e.id)} aria-expanded={open === e.id}>
                <span />
                <div>
                  <div className="list-title">{e.name}</div>
                  <div className="list-meta num">{e.sessions} sessions{e.mapped ? "" : " · not tagged"}</div>
                </div>
                <div className="list-metric num">{e.best_e1rm ? `${e.best_e1rm} kg` : ""}</div>
              </button>
              {open === e.id && progress && progress.sessions.length > 0 && (
                <SeriesChart title="Best est. 1RM per session" points={progress.sessions.map((s) => ({ x: dayMs(s.date), y: s.best_e1rm }))}
                  colorVar="--sport-gym" formatX={shortDate} formatY={(y) => `${y.toFixed(1)} kg`} formatTick={(y) => `${Math.round(y)}`} height={150} />
              )}
            </li>
          ))}
        </ul>
      </section>
      {unmapped.length > 0 && (
        <section className="card">
          <h2>Tag your exercises</h2>
          <p className="secondary" style={{ marginTop: 0 }}>These aren't in the exercise library yet, so they don't count toward muscle coverage.</p>
          {unmapped.map((e) => <TagForm key={e.id} exercise={e} muscles={muscles} onSaved={load} />)}
        </section>
      )}
    </>
  );
}

export default function Trends() {
  const { sport = "bike" } = useParams();
  const navigate = useNavigate();
  const tab = (TABS.some((t) => t.key === sport) ? sport : "bike") as Tab;
  return (
    <>
      <h1>Trends</h1>
      <div className="chips" role="tablist" aria-label="Sport">
        {TABS.map((t) => (
          <button key={t.key} role="tab" className="chip" aria-pressed={tab === t.key} aria-selected={tab === t.key}
            onClick={() => navigate(`/trends/${t.key}`)}>{t.label}</button>
        ))}
      </div>
      {tab === "bike" && <Bike />}
      {tab === "run" && <Run />}
      {tab === "swim" && <Swim />}
      {tab === "gym" && <Gym />}
    </>
  );
}
