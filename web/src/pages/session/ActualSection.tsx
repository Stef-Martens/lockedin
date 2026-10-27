import { Card, SectionHead, Tile } from "../../components/ui";
import { formatDuration, formatMin, formatSportPace } from "../../lib/format";
import { statusLabel, type SessionDetail, type Status } from "../../lib/session";
import { PaceChart, RideChart } from "./charts";

function StatusText({ status }: { status: Status }) {
  const s = statusLabel(status);
  return <span className={`status-${s.tone}`}>{s.text}</span>;
}

/** What you did, next to the plan: tiles, the ride or pace chart, and a table per part, split or exercise. */
export default function ActualSection({ d }: { d: SessionDetail }) {
  const a = d.actual!;
  const { plan, item } = d;
  if (item.sport === "bike") {
    const work = (a.parts ?? []).filter((p) => p.avg_w != null);
    const avgWork = work.length ? Math.round(work.reduce((s, p) => s + (p.avg_w ?? 0), 0) / work.length) : null;
    const all = a.parts ?? [];
    const onTarget = all.filter((p) => p.status === "on_target").length;
    return (
      <>
        <div className="tiles">
          <Tile label="Time" value={formatMin(a.moving_s ?? a.duration_s)} hint={plan.kind === "zwift" ? `planned ${formatMin(plan.duration_s)}` : undefined} i={0} />
          <Tile label="Avg power" value={a.avg_power ? `${a.avg_power} W` : "–"} i={1} />
          {avgWork != null && <Tile label="Intervals" value={`${avgWork} W`} hint={all.some((p) => p.target_w) ? `${onTarget} of ${all.length} on target` : undefined} i={2} />}
          <Tile label="Avg HR" value={a.avg_hr ? `${a.avg_hr}` : "–"} i={3} />
          <Tile label="TSS" value={a.tss ? String(Math.round(a.tss)) : "–"} hint={plan.kind === "zwift" ? `planned ${plan.tss_est}` : undefined} i={4} />
        </div>
        {plan.kind === "zwift" && a.power && (
          <Card i={3}>
            <SectionHead title="Plan vs what you rode" right={<span className="legend"><span><i className="swatch" style={{ background: "var(--series-power)" }} />Your power</span><span><i className="swatch" style={{ background: "var(--accent)" }} />Target</span><span><i className="swatch" style={{ background: "var(--series-hr)" }} />Heart rate</span></span>} />
            <RideChart parts={plan.parts} a={a} ftp={plan.ftp} />
          </Card>
        )}
        {a.parts && a.parts.length > 0 && (
          <Card i={4}>
            <SectionHead title="Interval by interval" />
            <div className="table-wrap">
              <table className="table" aria-label="Interval by interval">
                <thead><tr><th>Part</th><th className="num">Target</th><th className="num">You</th><th className="num">HR</th><th className="num">Cadence</th><th /></tr></thead>
                <tbody>
                  {a.parts.map((p) => (
                    <tr key={p.label}><td>{p.label}</td><td className="num">{p.target_w ? `${p.target_w} W` : "–"}</td>
                      <td className="num">{p.avg_w != null ? `${p.avg_w} W` : "–"}</td><td className="num">{p.avg_hr ?? "–"}</td>
                      <td className="num">{p.avg_cadence ?? "–"}</td><td><StatusText status={p.status} /></td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small-print">On target means within 3% of the target{plan.kind === "zwift" && plan.ftp ? `, using your FTP of ${plan.ftp} W` : ""}.</p>
          </Card>
        )}
      </>
    );
  }
  if (item.sport === "run" || item.sport === "swim") {
    const sport = item.sport;
    const t = plan.kind === "targets" ? plan : undefined;
    const pace = sport === "run" ? a.avg_pace_s_per_km : a.swim_pace_s_per_100m;
    const zoneTotal = a.zones ? Object.values(a.zones).reduce((s, v) => s + v, 0) : 0;
    return (
      <>
        <div className="tiles">
          <Tile label="Distance" value={a.distance_m ? (sport === "run" ? `${(a.distance_m / 1000).toFixed(2)} km` : `${Math.round(a.distance_m)} m`) : "–"}
            hint={t?.distance_m ? `planned ${sport === "run" ? `${(t.distance_m / 1000).toFixed(1)} km` : `${t.distance_m} m`}` : undefined} i={0} />
          <Tile label="Time" value={formatMin(a.moving_s ?? a.duration_s)} hint={t?.duration_s ? `planned ${formatMin(t.duration_s)}` : undefined} i={1} />
          <Tile label="Pace" value={formatSportPace(pace, sport)} hint={t?.pace_low && t.pace_high ? `target ${formatDuration(t.pace_low)}–${formatDuration(t.pace_high)}` : undefined} i={2} />
          <Tile label="Avg HR" value={a.avg_hr ? `${a.avg_hr}` : "–"} hint={t && "hr_bpm" in t && t.hr_bpm ? `zone ${t.hr_zone}: ${t.hr_bpm[0]}–${t.hr_bpm[1]}` : undefined} i={3} />
          {sport === "swim" && a.swim_lengths && <Tile label="Lengths" value={String(a.swim_lengths)} i={4} />}
          {sport === "swim" && a.swim_strokes && <Tile label="Strokes" value={String(a.swim_strokes)} i={5} />}
        </div>
        {sport === "run" && a.pace && (
          <Card i={3}><SectionHead title="Pace" /><PaceChart a={a} low={t?.pace_low} high={t?.pace_high} /></Card>
        )}
        {a.splits && (
          <Card i={4}>
            <SectionHead title="Splits" />
            <div className="table-wrap">
              <table className="table" aria-label="Splits">
                <thead><tr><th>Km</th><th className="num">Pace</th><th className="num">HR</th><th /></tr></thead>
                <tbody>{a.splits.map((s) => (
                  <tr key={s.km}><td>{s.km}</td><td className="num">{formatSportPace(s.pace, "run")}</td><td className="num">{s.avg_hr ?? "–"}</td>
                    <td>{s.status ? <StatusText status={s.status} /> : null}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        )}
        {a.zones && zoneTotal > 0 && (
          <Card i={5}>
            <SectionHead title="Time in heart-rate zones" />
            {Object.entries(a.zones).map(([z, s]) => (
              <div key={z} className="zone-row">
                <span>Zone {z}</span>
                <span className="zone-bar"><span className="grow-x" style={{ width: `${(s / zoneTotal) * 100}%` }} /></span>
                <span className="num secondary">{formatMin(s)}</span>
              </div>
            ))}
          </Card>
        )}
      </>
    );
  }
  if (item.sport === "gym" && a.rows) {
    return (
      <Card i={2}>
        <SectionHead title="Plan vs what you did" />
        <div className="table-wrap">
          <table className="table" aria-label="Plan vs what you did">
            <thead><tr><th>Exercise</th><th>Planned</th><th>Did</th><th /></tr></thead>
            <tbody>
              {a.rows.map((r, n) => (
                <tr key={`${r.exercise}-${n}`} className={r.status === "skipped_by_you" ? "muted-row" : ""}>
                  <td><strong>{r.exercise}</strong>{r.extra && <span className="muted"> · extra</span>}{r.goal && <span className="goal-tag">{r.goal}</span>}</td>
                  <td className="num">{r.planned ? `${r.planned.sets} × ${r.planned.reps}${r.planned.weight_kg != null ? ` at ${r.planned.weight_kg} kg` : ""}` : "–"}</td>
                  <td className="num">{r.done.length ? r.done.map((s) => `${s.kg ?? "BW"}×${s.reps ?? 0}`).join(" · ") : "–"}</td>
                  <td><StatusText status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    );
  }
  return null;
}
