import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCssVar } from "../lib/useCssVar";

export interface Point {
  x: number;
  y: number | null;
}

interface Props {
  title: string;
  summary?: string;
  points: Point[];
  colorVar: string;
  formatX: (x: number) => string;
  formatY: (y: number) => string;
  /** Axis ticks stay bare numbers; the unit lives in the title/summary. Defaults to formatY. */
  formatTick?: (y: number) => string;
  xType?: "number" | "category";
  reversed?: boolean;
  height?: number;
}

/** One series per chart: different measures never share an axis. */
export default function SeriesChart({ title, summary, points, colorVar, formatX, formatY, formatTick, xType = "number",
  reversed = false, height = 180 }: Props) {
  const color = useCssVar(colorVar);
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const axis = useCssVar("--axis");
  const surface = useCssVar("--surface");
  const tick = { fill: muted, fontSize: 12 };

  return (
    <div className="card">
      <div className="chart-title">
        <h2>{title}</h2>
        {summary && <span className="secondary num">{summary}</span>}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={points} margin={{ top: 12, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={grid} />
          <XAxis dataKey="x" type={xType} domain={["dataMin", "dataMax"]} tickFormatter={formatX} tick={tick}
            stroke={axis} tickLine={false} minTickGap={24} />
          <YAxis tickFormatter={formatTick ?? formatY} tick={tick} axisLine={false} tickLine={false} width={40}
            reversed={reversed} domain={["auto", "auto"]} />
          <Tooltip
            cursor={{ stroke: axis }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as Point | undefined;
              if (!active || !p || p.y == null) return null;
              return (
                <div className="chart-tooltip num">
                  <div className="muted">{formatX(p.x)}</div>
                  <div><strong>{formatY(p.y)}</strong></div>
                </div>
              );
            }}
          />
          <Line type="monotone" dataKey="y" stroke={color} strokeWidth={2} dot={false}
            activeDot={{ r: 4, stroke: surface, strokeWidth: 2 }} isAnimationActive={false}
            connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
