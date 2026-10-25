import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import SeriesChart, { type Point } from "../components/SeriesChart";
import { Card, PageHeader } from "../components/ui";
import { activityTitle } from "../lib/activity";
import { apiFetch } from "../lib/api";
import { formatDuration, formatPace, formatSwimPace, formatDistance, SPORT_LABEL } from "../lib/format";
import { stagger } from "../lib/motion";
import { smooth } from "../lib/smooth";
import type { ActivityDetail as Detail, GymSet, Profile } from "../lib/types";

const minutes = (s: number) => `${Math.round(s / 60)}′`;
// Hevy's own markers: warm-up, failure, drop set.
const SET_MARK: Record<string, string> = { warmup: "W", failure: "F", dropset: "D" };
const SOURCE: Record<string, string> = { zwift: "Zwift", healthfit: "Apple Watch", hevy: "Hevy" };

function series(t: number[], ys: (number | null)[] | null, map: (y: number) => number | null = (y) => y): Point[] | null {
  if (!ys || !ys.some((y) => y != null)) return null;
  return t.map((x, i) => ({ x, y: ys[i] == null ? null : map(ys[i] as number) }));
}

function GymCards({ sets }: { sets: GymSet[] }) {
  const groups: GymSet[][] = [];
  sets.forEach((s) => {
    const last = groups[groups.length - 1];
    if (last && last[0].exercise_order === s.exercise_order) last.push(s);
    else groups.push([s]);
  });
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "420px" }}>
        {groups.map((g, gi) => {
          const top = Math.max(0, ...g.map((s) => s.e1rm ?? 0));
          return (
            <Card key={g[0].exercise_order} i={gi + 2}>
              <div className="section-head" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 16, fontWeight: 600 }}>{g[0].exercise}</span>
                <span className="muted" style={{ fontSize: 13 }}>{top ? `best ${top.toFixed(1)} kg` : "bodyweight"}</span>
              </div>
              {g[0].notes && <div className="muted" style={{ fontSize: 13, marginTop: -4, marginBottom: 6 }}>{g[0].notes}</div>}
              <div className="set-row head"><span>Set</span><span className="r">kg</span><span className="r">Reps</span><span>Est. 1RM</span></div>
              {g.map((s, si) => (
                <div key={s.set_index} className="set-row">
                  <span className="secondary" title={s.set_type}>{s.set_index + 1}{SET_MARK[s.set_type] && <span className="muted"> {SET_MARK[s.set_type]}</span>}</span>
                  <span className="r display num" style={{ fontSize: 19, fontWeight: 600 }}>{s.weight_kg ?? <span className="muted" style={{ fontSize: 14 }}>BW</span>}</span>
                  <span className="r num">{s.reps ?? (s.duration_s ? formatDuration(s.duration_s) : "–")}</span>
                  <span className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
                    <span style={{ flex: 1, height: 6, background: "var(--hairline)", borderRadius: 3, overflow: "hidden" }}>
                      <span className="grow-x" style={{ display: "block", height: "100%", borderRadius: 3, background: "var(--sport-gym)",
                        width: top && s.e1rm ? `${(s.e1rm / top) * 100}%` : "0%", animationDelay: `${0.3 + gi * 0.05 + si * 0.06}s` }} />
                    </span>
                    <span className="num" style={{ width: 44, textAlign: "right", color: "var(--ink-2)" }}>{s.e1rm ? s.e1rm.toFixed(1) : "–"}</span>
                  </span>
                </div>
              ))}
            </Card>
          );
        })}
      </div>
      <p className="muted" style={{ fontSize: 13, margin: 0 }}>Weights as logged in Hevy. W warm-up · F to failure · D drop set · BW bodyweight · e1RM estimated 1-rep max</p>
    </>
  );
}

export default function ActivityDetail() {
  const { id } = useParams();
  const [a, setA] = useState<Detail | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setA(null);
    apiFetch<Detail>(`/api/activities/${id}`).then(setA).catch((e) => setError(e.message));
    apiFetch<Profile>("/api/profile").then(setProfile).catch(() => undefined);
  }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!a) return <p className="muted">Loading…</p>;

  const s = a.streams;
  const t = s?.t_offset ?? [];
  // ~30 s moving average for display only; the stored data and the tiles stay exact
  const step = t.length > 1 ? (t[t.length - 1] - t[0]) / (t.length - 1) : 1;
  const win = Math.max(1, Math.round(30 / step));
  const smoothed = (p: Point[] | null) => (p ? smooth(p, win) : null);
  const power = smoothed(series(t, s?.power ?? null));
  const hr = series(t, s?.hr ?? null);
  const cadence = a.sport === "bike" ? smoothed(series(t, s?.cadence ?? null)) : null;
  const pace = a.sport === "run" ? smoothed(series(t, s?.speed ?? null, (v) => (v > 0.5 ? 1000 / v : null))) : null;
  const when = new Date(a.start_at).toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Brussels" });
  const tiles: [string, string | null][] = [
    ["Time", formatDuration(a.moving_s ?? a.duration_s)],
    ["Distance", a.distance_m ? formatDistance(a.distance_m, a.sport) : null],
    ["Avg power", a.avg_power ? `${a.avg_power} W` : null],
    ["Norm. power", a.np ? `${Math.round(a.np)} W` : null],
    ["TSS", a.tss ? `${Math.round(a.tss)}` : null],
    ["Pace", a.avg_pace_s_per_km ? formatPace(a.avg_pace_s_per_km) : null],
    ["Pace", a.swim_pace_s_per_100m ? formatSwimPace(a.swim_pace_s_per_100m) : null],
    ["Lengths", a.swim_lengths && a.pool_length_m ? `${a.swim_lengths} × ${a.pool_length_m} m` : null],
    ["Strokes", a.swim_strokes ? `${a.swim_strokes}` : null],
    ["Avg HR", a.avg_hr ? `${a.avg_hr} bpm` : null],
    ["Max HR", a.max_hr ? `${a.max_hr} bpm` : null],
    // FIT running cadence counts one leg (strides/min); steps per minute is double that
    ["Cadence", a.avg_cadence && a.sport !== "swim" ? (a.sport === "run" ? `${a.avg_cadence * 2} spm` : `${a.avg_cadence} rpm`) : null],
    ["Climbing", a.elevation_m ? `${Math.round(a.elevation_m)} m` : null],
    ["Calories", a.calories ? `${a.calories} kcal` : null],
    ["Sets", a.set_count ? `${a.set_count}` : null],
  ];
  const shown = tiles.filter(([, v]) => v);
  const ftpEstimated = a.sport === "bike" && a.if_ && a.np && profile && !profile.ftp_override;
  const effort = a.if_ ? (a.if_ < 0.75 ? "easy" : a.if_ <= 0.88 ? "steady" : "hard") : null;

  return (
    <>
      <Link to="/activities" className="secondary" style={{ fontSize: 14, textDecoration: "none" }}>Back to activities</Link>
      <PageHeader
        eyebrow={<span className="row" style={{ gap: 8 }}><span className="dot" style={{ background: `var(--sport-${a.sport})` }} />{SPORT_LABEL[a.sport]} · {SOURCE[a.source]}</span>}
        title={activityTitle(a)} sub={when} />

      {a.superseded_by_summary && (
        <div className="note rise" style={stagger(0)}>
          This Apple Watch recording duplicates <Link to={`/activities/${a.superseded_by_summary.id}`}>{activityTitle(a.superseded_by_summary)}</Link>, so it isn't counted.
        </div>
      )}
      {a.hr_merged_from_summary && (
        <div className="note rise" style={stagger(0)}>Heart rate comes from your <Link to={`/activities/${a.hr_merged_from_summary.id}`}>Apple Watch recording</Link>.</div>
      )}
      {a.duplicates.length > 0 && !a.hr_merged_from_summary && (
        <div className="note rise" style={stagger(0)}>Also recorded by your <Link to={`/activities/${a.duplicates[0].id}`}>Apple Watch</Link>; only this one counts.</div>
      )}

      <div className="tiles">
        {shown.map(([label, value], n) => (
          <div key={label + n} className="tile rise" style={stagger(n, 0.05, 0.03)}>
            <div className="label">{label}</div>
            <div className="value num">{value}</div>
          </div>
        ))}
      </div>

      {(power || hr || pace || cadence) && (
        <Card i={3}>
          {power && <SeriesChart bare syncId="act" title="Power" summary={a.avg_power ? `avg ${a.avg_power} W · 30 s smoothed` : undefined} points={power}
            colorVar="--series-power" formatX={minutes} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} i={0} />}
          {pace && <SeriesChart bare syncId="act" title="Pace" points={pace} colorVar="--series-pace" reversed formatX={minutes}
            formatY={(y) => formatPace(y)} formatTick={(y) => formatPace(y).replace(" /km", "")}
            summary={a.avg_pace_s_per_km ? `avg ${formatPace(a.avg_pace_s_per_km)}` : undefined} i={0} />}
          {hr && <SeriesChart bare syncId="act" title="Heart rate" summary={a.avg_hr ? `avg ${a.avg_hr} bpm` : undefined} points={hr}
            colorVar="--series-hr" formatX={minutes} formatY={(y) => `${Math.round(y)} bpm`} formatTick={(y) => `${Math.round(y)}`} height={170} i={1} />}
          {cadence && <SeriesChart bare syncId="act" title="Cadence" summary={a.avg_cadence ? `avg ${a.avg_cadence} rpm` : undefined}
            points={cadence} colorVar="--series-cadence" formatX={minutes} formatY={(y) => `${Math.round(y)} rpm`}
            formatTick={(y) => `${Math.round(y)}`} height={130} i={2} />}
        </Card>
      )}

      {effort && a.np && a.if_ && (
        <div className="note rise row spread" style={stagger(4)}>
          <span>Effort: <strong style={{ color: "var(--ink)" }}>{effort}</strong> · intensity {a.if_.toFixed(2)}
            {ftpEstimated ? ` against an estimated FTP of ${Math.round(a.np / a.if_)} W. Enter your Zwift FTP for accurate numbers.` : "."}</span>
          {ftpEstimated && <Link to="/body" style={{ fontWeight: 600, textDecoration: "none" }}>Set FTP</Link>}
        </div>
      )}

      {a.sets && <GymCards sets={a.sets} />}
    </>
  );
}
