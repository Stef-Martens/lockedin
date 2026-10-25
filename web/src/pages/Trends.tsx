import { type FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import MuscleCoverage from "../components/MuscleCoverage";
import SeriesChart, { type Point } from "../components/SeriesChart";
import { Card, PageHeader, SectionHead } from "../components/ui";
import WeeklyBars from "../components/WeeklyBars";
import { apiFetch } from "../lib/api";
import type { Coverage, EffortMix, FocusItem } from "../lib/focus";
import { formatPace, formatSwimPace } from "../lib/format";
import { stagger } from "../lib/motion";
import type { Profile } from "../lib/types";

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

function Failed({ retry }: { retry: () => void }) {
  return (
    <Card>
      <p style={{ marginTop: 0 }}>Couldn't load this right now. Check your connection.</p>
      <button className="btn" onClick={retry}>Try again</button>
    </Card>
  );
}

/** Fetch with loading / failed / data states, so a bad connection never looks like "no data". */
function useLoad<T>(path: string): { data: T | null; failed: boolean; retry: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  const [n, setN] = useState(0);
  useEffect(() => {
    setFailed(false);
    apiFetch<T>(path).then(setData).catch(() => setFailed(true));
  }, [path, n]);
  return { data, failed, retry: () => setN(n + 1) };
}

function useFocusSessions(): SessionItem[] {
  const [items, setItems] = useState<SessionItem[]>([]);
  useEffect(() => {
    apiFetch<{ session_suggestions: Omit<SessionItem, "type">[] }>("/api/focus")
      .then((f) => setItems(f.session_suggestions.map((s) => ({ type: "session" as const, ...s })))).catch(() => undefined);
  }, []);
  return items;
}

/** Empty state with a soft preview of the charts that will appear. */
function Empty({ what, charts }: { what: string; charts: string[] }) {
  return (
    <>
      <Card i={1} className="row spread">
        <div style={{ maxWidth: 560 }}>
          <h2 style={{ fontSize: 30, margin: 0 }}>No {what} yet</h2>
          <p style={{ margin: "8px 0 0", lineHeight: 1.5, color: "var(--ink-2)" }}>
            {what === "gym workouts"
              ? "Upload your Hevy export on the Import page and your sets, muscle coverage and progress show up here."
              : `${what[0].toUpperCase()}${what.slice(1)} come from your Apple Watch through HealthFit. Once its iCloud folder is in your sync settings, past and new ones land here automatically.`}
          </p>
        </div>
        <Link to="/import" className="btn primary" style={{ textDecoration: "none" }}>Check sync status</Link>
      </Card>
      <div className="grid-auto" aria-hidden="true" style={{ ["--min" as string]: "300px" }}>
        {charts.map((c, n) => (
          <Card key={c} i={n + 2}>
            <h2 className="muted" style={{ fontSize: 18 }}>{c}</h2>
            <svg className="ghost" viewBox="0 0 400 140" style={{ width: "100%", height: "auto", animationDelay: `${n * 0.3}s` }}>
              <polyline points={n % 2 ? "10,110 80,96 150,100 220,80 290,84 390,64" : "10,100 70,90 130,104 190,76 260,82 330,62 390,58"}
                fill="none" stroke="#3a3e42" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" />
            </svg>
          </Card>
        ))}
      </div>
    </>
  );
}

function MixBar({ mix, i }: { mix: EffortMix; i?: number }) {
  const order = ["easy", "steady", "long", "hard"] as const;
  const colors = { easy: "#3ccf9a", steady: "#4d97ec", long: "#a68cff", hard: "#ff7a45" };
  const total = order.reduce((t, k) => t + mix.counts[k], 0);
  return (
    <div className="card rise" style={stagger(i ?? 0)}>
      <div className="eyebrow">Last 4 weeks by effort</div>
      {total ? (
        <>
          <div style={{ display: "flex", height: 12, borderRadius: 6, overflow: "hidden", marginTop: 18, background: "var(--hairline)", gap: 2 }}>
            {order.filter((k) => mix.counts[k]).map((k) => (
              <div key={k} className="grow-x" style={{ width: `${(mix.counts[k] / total) * 100}%`, background: colors[k], animationDelay: ".4s" }} />
            ))}
          </div>
          <div className="row spread" style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 10, gap: 8 }}>
            {order.map((k) => (
              <span key={k} className="row" style={{ gap: 6, color: mix.counts[k] ? "var(--ink)" : undefined }}>
                <span className="dot" style={{ background: colors[k], width: 8, height: 8 }} />{k[0].toUpperCase() + k.slice(1)} {mix.counts[k]}
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="secondary" style={{ margin: "12px 0 0", fontSize: 14 }}>No heart-rate or power data to classify yet.</p>
      )}
    </div>
  );
}

function TryThis({ items, sport, i }: { items: SessionItem[]; sport: string; i?: number }) {
  const mine = items.filter((s) => s.sport === sport);
  if (!mine.length) return null;
  return (
    <Card variant="accent" i={i}>
      <div className="eyebrow" style={{ color: "var(--accent)", fontWeight: 600 }}>Try this</div>
      {mine.map((s, n) => (
        <div key={n} style={{ marginTop: 6, fontSize: 16 }}><strong>{s.title}</strong>: {s.detail} <span className="secondary">· {s.reason.toLowerCase()}</span></div>
      ))}
    </Card>
  );
}

interface BikeData { rides: { date: string; np: number | null; efficiency: number | null; best_20m: number | null }[]; ftp: number | null; mix: EffortMix }
function Bike() {
  const { data: d, failed, retry } = useLoad<BikeData>("/api/trends/bike");
  const { data: profile } = useLoad<Profile>("/api/profile");
  const sugg = useFocusSessions();
  if (failed) return <Failed retry={retry} />;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.rides.length) return <Empty what="rides" charts={["Normalized power", "Efficiency", "Best 20-min power"]} />;
  const bests = d.rides.map((r) => r.best_20m ?? 0);
  const best = Math.max(...bests);
  const before = Math.max(0, ...bests.slice(0, bests.lastIndexOf(best)));
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "240px" }}>
        <div className="card rise" style={stagger(1)}>
          <div className="eyebrow">FTP · {profile?.ftp_override ? "yours" : "estimated"}</div>
          <div className="display num" style={{ fontSize: 48, marginTop: 10 }}>{profile?.ftp_override ?? (d.ftp ? Math.round(d.ftp) : "–")} W</div>
          {!profile?.ftp_override && <div className="secondary" style={{ fontSize: 13, marginTop: 6 }}>95% of your best 20 min. <Link to="/body" style={{ textDecoration: "none" }}>Set your Zwift FTP</Link></div>}
        </div>
        <div className="card rise" style={stagger(2)}>
          <div className="eyebrow">Best 20-min power</div>
          <div className="row" style={{ gap: 10, marginTop: 10, alignItems: "baseline" }}>
            <span className="display num" style={{ fontSize: 48, color: "var(--accent)" }}>{Math.round(best)} W</span>
            {before > 0 && best > before && <span className="secondary" style={{ fontSize: 14 }}>+{Math.round(best - before)} W vs previous best</span>}
          </div>
        </div>
        <MixBar mix={d.mix} i={3} />
      </div>
      <TryThis items={sugg} sport="bike" i={4} />
      <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
        <SeriesChart title="Normalized power" summary="per ride" points={pts(d.rides, (r) => r.date, (r) => r.np)} colorVar="--series-power"
          formatX={shortDate} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} i={5} />
        <SeriesChart title="Efficiency" summary="power ÷ heart rate · higher = fitter" points={pts(d.rides, (r) => r.date, (r) => r.efficiency)}
          colorVar="--series-cadence" formatX={shortDate} formatY={(y) => y.toFixed(2)} i={6} />
        <SeriesChart title="Best 20-min power" summary="per ride" points={pts(d.rides, (r) => r.date, (r) => r.best_20m)} colorVar="--series-body"
          formatX={shortDate} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} i={7} />
      </div>
    </>
  );
}

interface RunData { runs: { date: string; pace_s_per_km: number | null; aerobic_efficiency: number | null }[]; weekly: { week_start: string; km: number }[]; mix: EffortMix }
function Run() {
  const { data: d, failed, retry } = useLoad<RunData>("/api/trends/run");
  const sugg = useFocusSessions();
  if (failed) return <Failed retry={retry} />;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.runs.length) return <Empty what="runs" charts={["Pace per run", "Aerobic efficiency", "Weekly distance"]} />;
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "300px" }}>
        <MixBar mix={d.mix} i={1} />
        <TryThis items={sugg} sport="run" i={2} />
      </div>
      <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
        <SeriesChart title="Pace per run" points={pts(d.runs, (r) => r.date, (r) => r.pace_s_per_km)} colorVar="--series-pace" reversed
          formatX={shortDate} formatY={(y) => formatPace(y)} formatTick={(y) => formatPace(y).replace(" /km", "")} i={3} />
        <SeriesChart title="Aerobic efficiency" summary="higher = fitter" points={pts(d.runs, (r) => r.date, (r) => r.aerobic_efficiency)}
          colorVar="--series-cadence" formatX={shortDate} formatY={(y) => y.toFixed(2)} i={4} />
      </div>
      <WeeklyBars title="Weekly distance" rows={d.weekly} dataKey="km" colorVar="--sport-run" format={(v) => `${v} km`} i={5} />
    </>
  );
}

interface SwimData { swims: { date: string; pace_s_per_100m: number | null }[]; weekly: { week_start: string; m: number }[] }
function Swim() {
  const { data: d, failed, retry } = useLoad<SwimData>("/api/trends/swim");
  if (failed) return <Failed retry={retry} />;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.swims.length) return <Empty what="swims" charts={["Weekly distance", "Pace per 100 m"]} />;
  return (
    <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
      <WeeklyBars title="Weekly distance" rows={d.weekly} dataKey="m" colorVar="--sport-swim" format={(v) => `${v} m`} i={1} />
      <SeriesChart title="Pace per 100 m" points={pts(d.swims, (r) => r.date, (r) => r.pace_s_per_100m)} colorVar="--sport-swim" reversed
        formatX={shortDate} formatY={(y) => formatSwimPace(y)} formatTick={(y) => formatSwimPace(y).replace(" /100m", "")} i={2} />
    </div>
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
    <form onSubmit={save} style={{ padding: "12px 0", borderTop: "1px solid var(--hairline)" }}>
      <div className="list-title" style={{ marginBottom: 8 }}>{exercise.name}</div>
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
      <div className="row" style={{ marginTop: 10 }}>
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
  const [exercises, setExercises] = useState<Exercise[] | null>(null);
  const [muscles, setMuscles] = useState<Muscle[]>([]);
  const [failed, setFailed] = useState(false);
  const [picked, setPicked] = useState<number | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);

  const load = () => {
    setFailed(false);
    Promise.all([
      apiFetch<{ coverage: Coverage[]; unmapped: string[] }>("/api/gym/coverage"),
      apiFetch<Omit<GymItem, "type">[]>("/api/gym/suggestions?limit=20"),
      apiFetch<typeof volume>("/api/gym/volume?weeks=12"),
      apiFetch<Exercise[]>("/api/gym/exercises"),
      apiFetch<Muscle[]>("/api/muscles"),
    ]).then(([c, s, v, e, m]) => {
      setCov(c);
      setSugg(s.map((x) => ({ type: "gym" as const, ...x })));
      setVolume(v);
      setExercises(e);
      setMuscles(m);
      setPicked((p) => p ?? e.find((x) => x.best_e1rm)?.id ?? null);
    }).catch(() => setFailed(true));
  };
  useEffect(load, []);
  useEffect(() => {
    setProgress(null);
    if (picked != null) apiFetch<Progress>(`/api/gym/exercises/${picked}`).then(setProgress).catch(() => undefined);
  }, [picked]);

  if (failed) return <Failed retry={load} />;
  if (!cov || !exercises) return <p className="muted">Loading…</p>;
  if (!exercises.length) return <Empty what="gym workouts" charts={["Muscle coverage", "Progress", "Weekly volume"]} />;
  const unmapped = exercises.filter((e) => !e.mapped);
  const withHistory = exercises.filter((e) => e.best_e1rm);
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
        {cov.coverage.length ? <MuscleCoverage coverage={cov.coverage} suggestions={sugg} i={1} />
          : <Card i={1}><p style={{ margin: 0 }}>No gym sessions in the last 4 weeks.</p></Card>}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card i={2}>
            <SectionHead title="Progress" right={
              <label className="field" style={{ minWidth: 220 }}>
                <span className="sr-only">Exercise</span>
                <select value={picked ?? ""} onChange={(e) => setPicked(Number(e.target.value))}>
                  {withHistory.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </label>
            } />
            {progress && progress.sessions.length > 0 ? (
              <>
                <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
                  <span className="display num" style={{ fontSize: 40, color: "var(--sport-gym)" }}>
                    {Math.max(...progress.sessions.map((s) => s.best_e1rm)).toFixed(1)} kg
                  </span>
                  <span className="secondary" style={{ fontSize: 14 }}>best est. 1RM · {progress.sessions.length} sessions</span>
                </div>
                <SeriesChart bare key={picked} title="" points={progress.sessions.map((s) => ({ x: dayMs(s.date), y: s.best_e1rm }))}
                  colorVar="--sport-gym" formatX={shortDate} formatY={(y) => `${y.toFixed(1)} kg`} formatTick={(y) => `${Math.round(y)}`} height={180} />
              </>
            ) : <p className="muted">Loading…</p>}
          </Card>
          <WeeklyBars title="Weekly volume" summary="kg × reps" rows={volume} dataKey="volume_kg" colorVar="--sport-gym"
            format={(v) => `${Math.round(v).toLocaleString("en-GB")} kg`} i={3} />
        </div>
      </div>
      {unmapped.length > 0 && (
        <Card i={4}>
          <SectionHead title="Tag your exercises" />
          <p className="secondary" style={{ marginTop: 0 }}>These aren't in the exercise library yet, so they don't count toward muscle coverage.</p>
          {unmapped.map((e) => <TagForm key={e.id} exercise={e} muscles={muscles} onSaved={load} />)}
        </Card>
      )}
    </>
  );
}

export default function Trends() {
  const { sport = "bike" } = useParams();
  const tab = (TABS.some((t) => t.key === sport) ? sport : "bike") as Tab;
  return (
    <>
      <PageHeader title="Trends" right={
        <nav className="segmented" aria-label="Sport">
          {TABS.map((t) => (
            <Link key={t.key} to={`/trends/${t.key}`} aria-current={tab === t.key ? "page" : undefined} style={{ minWidth: 72 }}>{t.label}</Link>
          ))}
        </nav>
      } />
      {tab === "bike" && <Bike />}
      {tab === "run" && <Run />}
      {tab === "swim" && <Swim />}
      {tab === "gym" && <Gym />}
    </>
  );
}
