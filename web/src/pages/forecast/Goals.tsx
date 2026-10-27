import { Link } from "react-router-dom";
import { Card, SectionHead } from "../../components/ui";
import { type GoalForecast, goalTick, goalValue, STATUS } from "../../lib/forecast";
import { dayMonthYear } from "../../lib/format";
import ProjectionChart, { ProjectionLegend } from "./ProjectionChart";

const COLOR: Record<GoalForecast["kind"], string> = {
  lift: "--sport-gym", ftp: "--series-power", distance: "--sport-run", time: "--series-pace", body: "--series-body",
};

function GoalCard({ g, i }: { g: GoalForecast; i: number }) {
  const s = STATUS[g.status];
  const thin = g.status === "too_little_data";
  const projection = thin ? [] : g.projection;
  const colorVar = COLOR[g.kind];
  const better = g.lower_is_better ? "lower is better, drawn so better is higher up" : "higher is better";
  return (
    <Card i={i} className="forecast-goal">
      <div className="row spread forecast-goal-head">
        <h3>{g.text}</h3>
        <span className={`pill ${s.pill}`}>{s.label}</span>
      </div>
      <p className="forecast-summary">{g.summary}</p>
      <div className="secondary num forecast-now">
        {g.current != null && <>Now {goalValue(g.current, g.unit)} · </>}target {goalValue(g.target, g.unit)}
        {g.deadline && <> by {dayMonthYear(g.deadline)}</>}
      </div>
      {g.history.length > 0 && (
        <>
          <ProjectionChart history={g.history} projection={projection} colorVar={colorVar}
            format={(v) => goalValue(v, g.unit)} tick={(v) => goalTick(v, g.unit)} reversed={g.lower_is_better}
            target={thin ? undefined : g.target} deadline={thin ? null : g.deadline}
            label={`${g.text}: so far${projection.length ? " and where it's heading" : ""}, ${better}${g.deadline && !thin ? `, deadline ${dayMonthYear(g.deadline)}` : ""}`} />
          <ProjectionLegend colorVar={colorVar} projected={projection.length > 0} />
        </>
      )}
    </Card>
  );
}

/** One card per measurable goal; with none, a pointer to the coach, where goals are set. */
export default function Goals({ goals }: { goals: GoalForecast[] }) {
  return (
    <section aria-labelledby="forecast-goals">
      <SectionHead title={<span id="forecast-goals">Goals</span>} />
      {goals.length ? (
        <div className="grid-auto" style={{ ["--min" as string]: "340px" }}>
          {goals.map((g, n) => <GoalCard key={g.goal_id} g={g} i={n + 1} />)}
        </div>
      ) : (
        <p className="secondary flush">Set a goal with the <Link to="/coach">coach</Link> and its forecast shows here.</p>
      )}
    </section>
  );
}
