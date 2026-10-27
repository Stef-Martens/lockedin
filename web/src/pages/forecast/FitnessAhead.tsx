import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { loadAxes, LoadLegend, LoadReadout, useLoadColors } from "../../components/LoadChart";
import { Card, SectionHead } from "../../components/ui";
import { aheadLine, type ForecastDay } from "../../lib/forecast";
import { dayMonth } from "../../lib/format";
import { prefersReducedMotion } from "../../lib/motion";

/**
 * Each line in two parts: done (solid) and planned (dashed). Today's value is in both, so they meet at today.
 */
function split(days: ForecastDay[], today: string | null) {
  return days.map((d) => {
    const past = !d.planned;
    const ahead = d.planned || d.day === today;
    return { ...d, fitPast: past ? d.fitness : null, fatPast: past ? d.fatigue : null,
      fitAhead: ahead ? d.fitness : null, fatAhead: ahead ? d.fatigue : null };
  });
}

/** Fitness and fatigue for the last four weeks and the planned two ahead, form below, the outlook in one line. */
export default function FitnessAhead({ days, i }: { days: ForecastDay[]; i: number }) {
  const c = useLoadColors();
  const animate = !prefersReducedMotion();
  const today = days.filter((d) => !d.planned).at(-1)?.day ?? null;
  const rows = split(days, today);
  const line = aheadLine(days);
  const { x, y } = loadAxes(c, dayMonth);
  const lineProps = { type: "monotone" as const, strokeWidth: 2, dot: false, isAnimationActive: animate, animationDuration: 900 };
  const ahead = { strokeDasharray: "5 4", strokeOpacity: 0.65 };
  const marker = today && <ReferenceLine x={today} stroke={c.muted} strokeDasharray="2 3" />;
  return (
    <Card i={i}>
      <SectionHead title="Fitness ahead" right={<LoadLegend c={c} />} />
      <div role="img" aria-label={`Fitness and fatigue over the last ${rows.filter((r) => !r.planned).length} days and the planned ${rows.filter((r) => r.planned).length} ahead`}>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 20, right: 8, bottom: 0, left: 0 }} syncId="ahead">
            <CartesianGrid vertical={false} stroke={c.grid} />
            <XAxis {...x} hide />
            <YAxis {...y} />
            <Tooltip cursor={{ stroke: "#5b6066" }} content={<LoadReadout />} />
            {today && <ReferenceLine x={today} stroke={c.muted} strokeDasharray="2 3"
              label={{ value: "Today", position: "top", fill: c.muted, fontSize: 11 }} />}
            <Line {...lineProps} dataKey="fitPast" stroke={c.fitness} />
            <Line {...lineProps} dataKey="fatPast" stroke={c.fatigue} />
            <Line {...lineProps} {...ahead} dataKey="fitAhead" stroke={c.fitness} activeDot={false} />
            <Line {...lineProps} {...ahead} dataKey="fatAhead" stroke={c.fatigue} activeDot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="eyebrow load-form-title">Form · fitness − fatigue</div>
      <div role="img" aria-label="Form per day: above the line fresh, below it tired; the faded bars are planned">
        <ResponsiveContainer width="100%" height={90}>
          <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} syncId="ahead" barCategoryGap={1}>
            <XAxis {...x} />
            <YAxis {...y} />
            <ReferenceLine y={0} stroke={c.axis} />
            {marker}
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={<LoadReadout />} />
            <Bar dataKey="form" fill={c.form} isAnimationActive={animate} animationDuration={700}>
              {rows.map((r) => <Cell key={r.day} fillOpacity={r.planned ? 0.4 : 1} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {line && <p className="forecast-summary forecast-ahead num">{line}</p>}
    </Card>
  );
}
