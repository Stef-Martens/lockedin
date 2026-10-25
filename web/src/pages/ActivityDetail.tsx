import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import SeriesChart, { type Point } from "../components/SeriesChart";
import SportDot from "../components/SportDot";
import { activityTitle } from "../lib/activity";
import { apiFetch } from "../lib/api";
import { formatDate, formatDistance, formatDuration, formatPace, formatSwimPace, SPORT_LABEL } from "../lib/format";
import type { ActivityDetail as Detail, GymSet } from "../lib/types";

const minutes = (s: number) => `${Math.round(s / 60)}′`;
// Hevy's own markers: warm-up, failure, drop set.
const SET_MARK: Record<string, string> = { warmup: "W", failure: "F", dropset: "D" };

function series(t: number[], ys: (number | null)[] | null, map: (y: number) => number | null = (y) => y): Point[] | null {
  if (!ys || !ys.some((y) => y != null)) return null;
  return t.map((x, i) => ({ x, y: ys[i] == null ? null : map(ys[i] as number) }));
}

function Tile({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
    </div>
  );
}

function GymTable({ sets }: { sets: GymSet[] }) {
  const groups: GymSet[][] = [];
  sets.forEach((s) => {
    const last = groups[groups.length - 1];
    if (last && last[0].exercise_order === s.exercise_order) last.push(s);
    else groups.push([s]);
  });
  return (
    <>
      {groups.map((g) => (
        <section className="card" key={g[0].exercise_order}>
          <h2>{g[0].exercise}</h2>
          {g[0].notes && <p className="muted" style={{ marginTop: -8 }}>{g[0].notes}</p>}
          <div className="table-wrap">
            <table className="table num">
              <thead>
                <tr><th>Set</th><th className="num">kg</th><th className="num">Reps</th><th className="num">RPE</th><th className="num" title="Estimated 1-rep max">e1RM</th></tr>
              </thead>
              <tbody>
                {g.map((s) => (
                  <tr key={s.set_index}>
                    <td title={s.set_type}>{s.set_index + 1}{SET_MARK[s.set_type] && <span className="muted"> {SET_MARK[s.set_type]}</span>}</td>
                    <td className="num">{s.weight_kg != null ? s.weight_kg : <span className="muted">BW</span>}</td>
                    <td className="num">{s.reps ?? (s.duration_s ? formatDuration(s.duration_s) : "–")}</td>
                    <td className="num">{s.rpe ?? ""}</td>
                    <td className="num">{s.e1rm ? s.e1rm.toFixed(1) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      <p className="muted" style={{ fontSize: "0.85rem" }}>W warm-up · F to failure · D drop set · BW bodyweight · e1RM estimated 1-rep max</p>
    </>
  );
}

export default function ActivityDetail() {
  const { id } = useParams();
  const [a, setA] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setA(null);
    apiFetch<Detail>(`/api/activities/${id}`).then(setA).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!a) return <p className="muted">Loading…</p>;

  const s = a.streams;
  const t = s?.t_offset ?? [];
  const power = series(t, s?.power ?? null);
  const hr = series(t, s?.hr ?? null);
  const cadence = a.sport === "bike" ? series(t, s?.cadence ?? null) : null;
  const pace = a.sport === "run" ? series(t, s?.speed ?? null, (v) => (v > 0.5 ? 1000 / v : null)) : null;
  const swimLengths = a.swim_lengths && a.pool_length_m ? `${a.swim_lengths} × ${a.pool_length_m} m` : null;

  return (
    <>
      <p style={{ margin: "0 0 8px" }}><Link to="/activities" className="secondary">← Activities</Link></p>
      <div className="row" style={{ gap: 8 }}>
        <SportDot sport={a.sport} />
        <span className="secondary">{SPORT_LABEL[a.sport]}</span>
      </div>
      <h1>{activityTitle(a)}</h1>
      <p className="secondary num" style={{ marginTop: 0 }}>{formatDate(a.start_at)}</p>

      {a.superseded_by_summary && (
        <p className="note">
          This Apple Watch recording is a duplicate of{" "}
          <Link to={`/activities/${a.superseded_by_summary.id}`}>{activityTitle(a.superseded_by_summary)}</Link>,
          so it isn't counted in your totals.
        </p>
      )}
      {a.hr_merged_from_summary && (
        <p className="note">
          Heart rate comes from your <Link to={`/activities/${a.hr_merged_from_summary.id}`}>Apple Watch recording</Link>.
        </p>
      )}

      <div className="tiles" style={{ marginTop: 16 }}>
        <Tile label="Time" value={formatDuration(a.moving_s ?? a.duration_s)} />
        <Tile label="Distance" value={a.distance_m ? formatDistance(a.distance_m, a.sport) : null} />
        <Tile label="Avg power" value={a.avg_power ? `${a.avg_power} W` : null} />
        <Tile label="Norm. power" value={a.np ? `${Math.round(a.np)} W` : null} />
        <Tile label="TSS" value={a.tss ? `${Math.round(a.tss)}` : null} />
        <Tile label="Pace" value={a.avg_pace_s_per_km ? formatPace(a.avg_pace_s_per_km) : null} />
        <Tile label="Pace" value={a.swim_pace_s_per_100m ? formatSwimPace(a.swim_pace_s_per_100m) : null} />
        <Tile label="Lengths" value={swimLengths} />
        <Tile label="Strokes" value={a.swim_strokes ? `${a.swim_strokes}` : null} />
        <Tile label="Avg HR" value={a.avg_hr ? `${a.avg_hr} bpm` : null} />
        <Tile label="Max HR" value={a.max_hr ? `${a.max_hr} bpm` : null} />
        <Tile label="Cadence" value={a.avg_cadence && a.sport !== "swim" ? `${a.avg_cadence} ${a.sport === "run" ? "spm" : "rpm"}` : null} />
        <Tile label="Climbing" value={a.elevation_m ? `${Math.round(a.elevation_m)} m` : null} />
        <Tile label="Calories" value={a.calories ? `${a.calories} kcal` : null} />
        <Tile label="Sets" value={a.set_count ? `${a.set_count}` : null} />
      </div>

      {power && <SeriesChart title="Power" summary={a.avg_power ? `avg ${a.avg_power} W` : undefined} points={power}
        colorVar="--series-power" formatX={minutes} formatY={(y) => `${Math.round(y)} W`}
        formatTick={(y) => `${Math.round(y)}`} />}
      {pace && <SeriesChart title="Pace" points={pace} colorVar="--series-pace" reversed formatX={minutes}
        formatY={(y) => formatPace(y).replace(" /km", "")} summary={a.avg_pace_s_per_km ? `avg ${formatPace(a.avg_pace_s_per_km)}` : undefined} />}
      {hr && <SeriesChart title="Heart rate" summary={a.avg_hr ? `avg ${a.avg_hr} bpm` : undefined} points={hr}
        colorVar="--series-hr" formatX={minutes} formatY={(y) => `${Math.round(y)} bpm`}
        formatTick={(y) => `${Math.round(y)}`} />}
      {cadence && <SeriesChart title="Cadence" summary={a.avg_cadence ? `avg ${a.avg_cadence} rpm` : undefined}
        points={cadence} colorVar="--series-cadence" formatX={minutes} formatY={(y) => `${Math.round(y)} rpm`}
        formatTick={(y) => `${Math.round(y)}`} height={140} />}

      {a.sets && <GymTable sets={a.sets} />}
    </>
  );
}
