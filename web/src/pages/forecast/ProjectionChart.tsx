import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dayMonth, dayMs } from "../../lib/format";
import type { Band, Point } from "../../lib/forecast";
import { prefersReducedMotion } from "../../lib/motion";
import { useCssVar } from "../../lib/useCssVar";
import { timeOffAreas } from "./timeOffAreas";

/** One x on the chart: what happened (`actual`) and/or what's likely next with its low–high range. */
interface Row { x: number; actual?: number; likely?: number; band?: [number, number] }

/**
 * History and projection on one time axis. The projection starts where the history ends, so when the server's
 * first projected week is later than the last real one, the last real value is the dashed line's first point.
 */
export function projectionRows(history: Point[], projection: Band[]): Row[] {
  const rows = new Map<string, Row>();
  const at = (day: string) => rows.get(day) ?? rows.set(day, { x: dayMs(day) }).get(day)!;
  for (const [day, v] of history) at(day).actual = v;
  const last = history[history.length - 1];
  if (projection.length && last && projection[0][0] > last[0]) Object.assign(at(last[0]), { likely: last[1], band: [last[1], last[1]] });
  for (const [day, likely, low, high] of projection) Object.assign(at(day), { likely, band: [low, high] });
  return [...rows.values()].sort((a, b) => a.x - b.x);
}

interface Props {
  history: Point[];
  projection: Band[];
  colorVar: string;
  /** A value with its unit, for the tooltip and the reference-line labels. */
  format: (v: number) => string;
  /** A bare value for the axis. */
  tick: (v: number) => string;
  label: string;
  target?: number;
  deadline?: string | null;
  /** Lower is better (times): flip the axis so getting better still reads as up, like the pace charts. */
  reversed?: boolean;
  /** Steps rather than slopes: a value that holds until it changes (FTP). */
  step?: boolean;
  /** Windows to shade behind the lines. */
  timeOff?: { start: string; end: string }[];
  height?: number;
}

export default function ProjectionChart({ history, projection, colorVar, format, tick, label, target, deadline,
  reversed = false, step = false, timeOff = [], height = 200 }: Props) {
  const color = useCssVar(colorVar);
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const ink3 = useCssVar("--ink-3");
  const axis = useCssVar("--axis");
  const surface = useCssVar("--surface");
  const animate = !prefersReducedMotion();
  const rows = projectionRows(history, projection);
  const sparse = history.length <= 30;
  const ref = { fill: ink3, fontSize: 11 };
  // Wide enough for the longest tick ("1:35:30"), ~7px a character at 12px.
  const values = [...history.map((p) => p[1]), ...projection.flatMap((b) => [b[2], b[3]]), ...(target != null ? [target] : [])];
  const yWidth = Math.max(40, ...values.map((v) => tick(v).length * 7 + 6));

  return (
    <div role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 20, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={grid} />
          <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={dayMonth} tick={{ fill: muted, fontSize: 12 }}
            stroke={axis} tickLine={false} minTickGap={24} />
          <YAxis tickFormatter={tick} tick={{ fill: muted, fontSize: 12 }} axisLine={false} tickLine={false} width={yWidth}
            reversed={reversed} domain={["auto", "auto"]} />
          <Tooltip cursor={{ stroke: "#5b6066" }} content={({ active, payload }) => {
            const r = payload?.[0]?.payload as Row | undefined;
            if (!active || !r) return null;
            return (
              <div className="chart-tooltip num">
                <div className="muted">{dayMonth(r.x)}</div>
                {r.actual != null ? <div><strong>{format(r.actual)}</strong></div> : r.likely != null && (
                  <>
                    <div>Likely <strong>{format(r.likely)}</strong></div>
                    {r.band && r.band[0] !== r.band[1] && <div className="muted">{format(r.band[0])} – {format(r.band[1])}</div>}
                  </>
                )}
              </div>
            );
          }} />
          {timeOffAreas(timeOff, muted, (d) => dayMs(d), rows.length ? [rows[0].x, rows[rows.length - 1].x] : null)}
          <Area dataKey="band" stroke="none" fill={color} fillOpacity={0.14} isAnimationActive={animate} animationDuration={900}
            activeDot={false} connectNulls />
          {target != null && (
            <ReferenceLine y={target} stroke={ink3} strokeDasharray="2 3" ifOverflow="extendDomain"
              label={{ value: `Target ${format(target)}`, position: "insideTopLeft", ...ref }} />
          )}
          {deadline && (
            <ReferenceLine x={dayMs(deadline)} stroke={ink3} ifOverflow="extendDomain"
              label={{ value: dayMonth(deadline), position: "insideTopRight", ...ref }} />
          )}
          <Line type={step ? "stepAfter" : "linear"} dataKey="actual" stroke={color} strokeWidth={2}
            dot={sparse ? { r: 3, fill: color, stroke: surface, strokeWidth: 2 } : false}
            activeDot={{ r: 5, stroke: surface, strokeWidth: 2 }} isAnimationActive={animate} animationDuration={900} />
          <Line type="linear" dataKey="likely" stroke={color} strokeWidth={2} strokeDasharray="5 4" strokeOpacity={0.8} dot={false}
            activeDot={{ r: 4, stroke: surface, strokeWidth: 2 }} isAnimationActive={animate} animationDuration={900} animationBegin={300} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The legend for a chart with a projection: so far, likely, likely range. */
export function ProjectionLegend({ colorVar, projected }: { colorVar: string; projected: boolean }) {
  const color = useCssVar(colorVar);
  if (!projected) return null;
  return (
    <span className="legend" aria-label="Legend">
      <span><i className="swatch" style={{ background: color }} />So far</span>
      <span><i className="swatch dashed" style={{ borderColor: color }} />Likely</span>
      <span><i className="swatch" style={{ background: color, opacity: 0.3 }} />Range</span>
    </span>
  );
}
