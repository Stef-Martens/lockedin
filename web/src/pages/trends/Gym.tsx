import { type ChangeEvent, type FormEvent, useState } from "react";
import MuscleCoverage from "../../components/MuscleCoverage";
import SeriesChart from "../../components/SeriesChart";
import { Card, SectionHead } from "../../components/ui";
import WeeklyBars from "../../components/WeeklyBars";
import { apiFetch } from "../../lib/api";
import type { Coverage, FocusItem } from "../../lib/focus";
import { dayMonth, dayMs } from "../../lib/format";
import { useApi, useLoad } from "../../lib/useApi";
import { Empty, Failed } from "./shared";

type GymItem = Extract<FocusItem, { type: "gym" }>;
interface Exercise { id: number; name: string; sessions: number; last_done: string; best_e1rm: number | null; mapped: boolean }
interface Muscle { key: string; name: string; region: string }
interface Progress { exercise: string; sessions: { date: string; best_e1rm: number }[] }
interface GymData {
  cov: { coverage: Coverage[]; unmapped: string[] };
  sugg: GymItem[];
  volume: { week_start: string; volume_kg: number }[];
  exercises: Exercise[];
  muscles: Muscle[];
}

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
  const pick = (setter: (v: string[]) => void) => (e: ChangeEvent<HTMLSelectElement>) =>
    setter(Array.from(e.target.selectedOptions).map((o) => o.value));
  return (
    <form onSubmit={save} className="tag-form">
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

export default function Gym() {
  const { data, error, reload } = useLoad<GymData>("gym", async (signal) => {
    const [cov, sugg, volume, exercises, muscles] = await Promise.all([
      apiFetch<GymData["cov"]>("/api/gym/coverage", { signal }),
      apiFetch<Omit<GymItem, "type">[]>("/api/gym/suggestions?limit=20", { signal }),
      apiFetch<GymData["volume"]>("/api/gym/volume?weeks=12", { signal }),
      apiFetch<Exercise[]>("/api/gym/exercises", { signal }),
      apiFetch<Muscle[]>("/api/muscles", { signal }),
    ]);
    return { cov, sugg: sugg.map((x) => ({ type: "gym" as const, ...x })), volume, exercises, muscles };
  });
  const [chosen, setChosen] = useState<number | null>(null);
  const picked = chosen ?? data?.exercises.find((x) => x.best_e1rm)?.id ?? null;
  // Switching exercises aborts the previous one, so a slow answer can't draw the wrong lift's chart.
  const progress = useApi<Progress>(picked != null ? `/api/gym/exercises/${picked}` : null);

  if (error) return <Failed retry={reload} />;
  if (!data) return <p className="muted">Loading…</p>;
  const { cov, sugg, volume, exercises, muscles } = data;
  if (!exercises.length) return <Empty what="gym workouts" charts={["Muscle coverage", "Progress", "Weekly volume"]} />;
  const unmapped = exercises.filter((e) => !e.mapped);
  const withHistory = exercises.filter((e) => e.best_e1rm);
  const p = progress.data;
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
        {cov.coverage.length ? <MuscleCoverage coverage={cov.coverage} suggestions={sugg} i={1} />
          : <Card i={1}><p className="flush">No gym sessions in the last 4 weeks.</p></Card>}
        <div className="column">
          <Card i={2}>
            <SectionHead title="Progress" right={
              <label className="field" style={{ minWidth: 220 }}>
                <span className="sr-only">Exercise</span>
                <select value={picked ?? ""} onChange={(e) => setChosen(Number(e.target.value))}>
                  {withHistory.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
              </label>
            } />
            {p && p.sessions.length > 0 ? (
              <>
                <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
                  <span className="display num" style={{ fontSize: 40, color: "var(--sport-gym)" }}>
                    {Math.max(...p.sessions.map((s) => s.best_e1rm)).toFixed(1)} kg
                  </span>
                  <span className="secondary" style={{ fontSize: 14 }}>best est. 1RM · {p.sessions.length} sessions</span>
                </div>
                <SeriesChart bare key={picked} title="" points={p.sessions.map((s) => ({ x: dayMs(s.date), y: s.best_e1rm }))}
                  colorVar="--sport-gym" formatX={dayMonth} formatY={(y) => `${y.toFixed(1)} kg`} formatTick={(y) => `${Math.round(y)}`} height={180} />
              </>
            ) : picked == null || (p && !p.sessions.length)
              ? <p className="secondary">No weighted sets yet to chart.</p>
              : progress.error ? <p className="error">Couldn't load this exercise. <button className="btn ghost" onClick={progress.reload}>Try again</button></p>
              : <p className="muted">Loading…</p>}
          </Card>
          <WeeklyBars title="Weekly volume" summary="kg × reps" rows={volume} dataKey="volume_kg" colorVar="--sport-gym"
            format={(v) => `${Math.round(v).toLocaleString("en-GB")} kg`} i={3} />
        </div>
      </div>
      {unmapped.length > 0 && (
        <Card i={4}>
          <SectionHead title="Tag your exercises" />
          <p className="secondary" style={{ marginTop: 0 }}>These aren't in the exercise library yet, so they don't count toward muscle coverage.</p>
          {unmapped.map((e) => <TagForm key={e.id} exercise={e} muscles={muscles} onSaved={reload} />)}
        </Card>
      )}
    </>
  );
}
