import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadAxes, LoadLegend, LoadReadout, useLoadColors } from "../../components/LoadChart";
import { Card, SectionHead, Tile } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { dayMonth } from "../../lib/format";
import { formNumber, formWords, loadNumber } from "../../lib/load";
import { prefersReducedMotion } from "../../lib/motion";
import type { TrainingLoad as LoadData } from "../../lib/types";
import { useApi } from "../../lib/useApi";

/**
 * Fitness (42-day average load) and fatigue (7-day) on one axis, form (the gap between them) as its own small
 * chart below, and today's three numbers in words. The endpoint may not exist yet: then this shows nothing.
 */
export default function TrainingLoad() {
  const { data, error } = useApi<LoadData>("/api/load");
  const c = useLoadColors();
  const { fitness, fatigue, form, grid, axis } = c;
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
  const { x, y } = loadAxes(c, dayMonth);
  return (
    <Card i={0}>
      <SectionHead title="Training load" right={<LoadLegend c={c} />} />
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
            <Tooltip cursor={{ stroke: "#5b6066" }} content={<LoadReadout />} />
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
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<LoadReadout />} />
            <Bar dataKey="form" fill={form} isAnimationActive={animate} animationDuration={700} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
