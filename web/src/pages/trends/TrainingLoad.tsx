import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, SectionHead, Tile } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { dayMonth, shortDay } from "../../lib/format";
import { formNumber, formWords, loadNumber } from "../../lib/load";
import { prefersReducedMotion } from "../../lib/motion";
import type { LoadDay, TrainingLoad as LoadData } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { useCssVar } from "../../lib/useCssVar";



function Readout({ active, payload }: { active?: boolean; payload?: { payload: LoadDay }[] }) {
  const r = payload?.[0]?.payload;
  if (!active || !r) return null;
  return (
    <div className="chart-tooltip num">
      <div className="muted">{shortDay(r.day)} · load {loadNumber(r.load)}</div>
      <div>Fitness <strong>{loadNumber(r.fitness)}</strong> · Fatigue <strong>{loadNumber(r.fatigue)}</strong></div>
      <div>Form <strong>{formNumber(r.form)}</strong> · {formWords(r.form).toLowerCase()}</div>
    </div>
  );
}

/**
 * Fitness (42-day average load) and fatigue (7-day) on one axis, form (the gap between them) as its own small
 * chart below, and today's three numbers in words. The endpoint may not exist yet: then this shows nothing.
 */
export default function TrainingLoad() {
  const { data, error } = useApi<LoadData>("/api/load");
  const fitness = useCssVar("--series-power");
  const fatigue = useCssVar("--series-pace");
  const form = useCssVar("--series-cadence");
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const axis = useCssVar("--axis");
  const animate = !prefersReducedMotion();

  if (error) {
    if (error instanceof ApiError && error.status === 404) return null;  // not on this server yet
    return <p className="muted quiet-note">Training load isn't available right now.</p>;
  }
  if (!data) return null;  // the sport charts below carry the loading state
  if (!data.today) {
    return (
      <Card i={0}>
        <SectionHead title="Training load" />
        <p className="secondary flush">Fitness, fatigue and form show up here once you've trained with heart rate or power for a while.</p>
      </Card>
    );
  }
  const rows = data.days;
  const t = data.today;
  const x = { dataKey: "day", tickFormatter: dayMonth,
    tick: { fill: muted, fontSize: 12 }, stroke: axis, tickLine: false, minTickGap: 24 };
  const y = { tick: { fill: muted, fontSize: 12 }, axisLine: false, tickLine: false, width: 40, allowDecimals: false };
  return (
    <Card i={0}>
      <SectionHead title="Training load" right={
        <span className="legend" aria-label="Legend">
          <span><i className="swatch" style={{ background: fitness }} />Fitness</span>
          <span><i className="swatch" style={{ background: fatigue }} />Fatigue</span>
          <span><i className="swatch" style={{ background: form }} />Form</span>
        </span>
      } />
      <div className="tiles">
        <Tile label="Fitness" value={loadNumber(t.fitness)} hint="your 6-week average load" dot={fitness} i={1} />
        <Tile label="Fatigue" value={loadNumber(t.fatigue)} hint="your last week's average load" dot={fatigue} i={2} />
        <Tile label="Form" value={formNumber(t.form)} hint={formWords(t.form)} dot={form} i={3} />
      </div>
      <div role="img" aria-label={`Fitness and fatigue over the last ${rows.length} days`}>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 16, right: 8, bottom: 0, left: 0 }} syncId="load">
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis {...x} hide />
            <YAxis {...y} />
            <Tooltip cursor={{ stroke: "#5b6066" }} content={<Readout />} />
            <Line type="monotone" dataKey="fitness" stroke={fitness} strokeWidth={2} dot={false} isAnimationActive={animate} animationDuration={900} />
            <Line type="monotone" dataKey="fatigue" stroke={fatigue} strokeWidth={2} dot={false} isAnimationActive={animate} animationDuration={900} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="eyebrow load-form-title">Form · fitness − fatigue</div>
      <div role="img" aria-label="Form per day: above the line fresh, below it tired">
        <ResponsiveContainer width="100%" height={90}>
          <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} syncId="load" barCategoryGap={1}>
            <XAxis {...x} />
            <YAxis {...y} />
            <ReferenceLine y={0} stroke={axis} />
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<Readout />} />
            <Bar dataKey="form" fill={form} isAnimationActive={animate} animationDuration={700} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
