import { Link } from "react-router-dom";
import { Card, SectionHead, Tile } from "../../components/ui";
import type { AgendaItem } from "../../lib/agenda";
import { formatDuration, formatMin, formatSportPace, todayLocal } from "../../lib/format";
import { changeLabel, doseLine, type PlanItem } from "../../lib/plan";
import type { SessionPlan } from "../../lib/session";
import { PlanChart } from "./charts";

/** What's planned: the Zwift workout, the run/swim targets, the gym routine, or just the note. */
export default function PlanSection({ plan, item }: { plan: SessionPlan; item: AgendaItem }) {
  if (plan.kind === "zwift") {
    return (
      <div className="session-grid">
        <Card i={2}>
          <SectionHead title="The workout" />
          <PlanChart parts={plan.parts} />
          <div className="table-wrap">
            <table className="table" aria-label="Workout parts">
              <thead><tr><th>Part</th><th className="num">Time</th><th className="num">Power</th></tr></thead>
              <tbody>
                {plan.parts.map((p, n) => (
                  <tr key={n} className={p.work ? "work-row" : ""}>
                    <td>{p.label}</td>
                    <td className="num">{formatDuration(p.start_s)}–{formatDuration(p.end_s)}</td>
                    <td className="num">{p.from_w == null
                      ? `${Math.round(p.from_frac * 100)}${p.to_frac !== p.from_frac ? ` → ${Math.round(p.to_frac * 100)}` : ""}%`
                      : `${p.from_w}${p.to_w !== p.from_w ? ` → ${p.to_w}` : ""} W`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="stack">
          <div className="tiles">
            <Tile label="Duration" value={formatMin(plan.duration_s)} i={0} />
            <Tile label="Sweet spot" value={`${plan.sweet_spot_min}′`} hint="at 84–97% FTP" i={1} />
            <Tile label="Est. TSS" value={String(plan.tss_est)} i={2} />
            <Tile label="FTP used" value={plan.ftp ? `${plan.ftp} W` : "–"} i={3} />
          </div>
          {!plan.ftp_is_set && <div className="note">These watts use an FTP estimated from your rides. Once you ride one of these workouts in ERG mode, LockedIn picks up Zwift's FTP and they match.</div>}
          {item.note && <Card i={3}><SectionHead title="Note" /><p className="secondary flush">{item.note}</p></Card>}
        </div>
      </div>
    );
  }
  if (plan.kind === "targets") {
    const sport = item.sport === "swim" ? "swim" : "run";
    return (
      <Card i={2}>
        <SectionHead title="The plan" />
        {item.plan_line && <p className="flush">{item.plan_line}</p>}
        <div className="tiles">
          {plan.distance_m && <Tile label="Distance" value={plan.distance_m >= 1000 ? `${(plan.distance_m / 1000).toFixed(1)} km` : `${plan.distance_m} m`} i={0} />}
          {plan.duration_s && <Tile label="Duration" value={formatMin(plan.duration_s)} i={1} />}
          {plan.pace_low && plan.pace_high && <Tile label="Pace" value={`${formatDuration(plan.pace_low)}–${formatSportPace(plan.pace_high, sport)}`} i={2} />}
          {plan.hr_zone && <Tile label="Heart rate" value={`Zone ${plan.hr_zone}`} hint={plan.hr_bpm ? `${plan.hr_bpm[0]}–${plan.hr_bpm[1]} bpm` : undefined} i={3} />}
        </div>
        {item.note && <p className="secondary" style={{ marginBottom: 0 }}>{item.note}</p>}
        {!plan.distance_m && !plan.duration_s && !plan.pace_low && !item.note && <p className="muted flush">No targets set. Use Edit to add some.</p>}
      </Card>
    );
  }
  if (plan.kind === "gym") {
    // Brussels' today: just after midnight UTC is still yesterday, which would hide "Plan it" for today.
    const upcoming = !item.done && item.day >= todayLocal();
    return (
      <Card i={2}>
        <SectionHead title="The plan" right={plan.routine && upcoming ? <Link to={`/plan?day=${encodeURIComponent(plan.routine)}`} className="btn primary small">Plan it</Link> : undefined} />
        {plan.items.length ? (
          <ul className="list">
            {plan.items.map((p: PlanItem) => (
              <li key={p.id} className="session-plan-row">
                <span><strong>{p.exercise}</strong>{p.kind === "add" && <span className="muted"> · extra</span>}</span>
                <span className="secondary num">{doseLine(p)}{changeLabel(p) ? ` · ${changeLabel(p)}` : ""}</span>
              </li>
            ))}
          </ul>
        ) : <p className="muted flush">Your routine shows here once it's in your Hevy history.</p>}
      </Card>
    );
  }
  return item.note ? <Card i={2}><p className="secondary flush">{item.note}</p></Card> : null;
}
