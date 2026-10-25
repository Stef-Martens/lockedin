import type { ReactNode } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { prefersReducedMotion } from "../lib/motion";
import { useCssVar } from "../lib/useCssVar";
import { Card } from "./ui";

export interface Point {
  x: number;
  y: number | null;
}

interface Props {
  title: string;
  summary?: ReactNode;
  points: Point[];
  colorVar: string;
  formatX: (x: number) => string;
  formatY: (y: number) => string;
  /** Axis ticks stay bare numbers; the unit lives in the title/summary. Defaults to formatY. */
  formatTick?: (y: number) => string;
  xType?: "number" | "category";
  reversed?: boolean;
  height?: number;
  /** Charts with the same syncId share one hover cursor (ride detail: power, HR, cadence). */
  syncId?: string;
  i?: number;
  bare?: boolean;
}

/** One series per chart: different measures never share an axis. */
export default function SeriesChart({ title, summary, points, colorVar, formatX, formatY, formatTick, xType = "number",
  reversed = false, height = 200, syncId, i, bare = false }: Props) {
  const color = useCssVar(colorVar);
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const axis = useCssVar("--axis");
  const surface = useCssVar("--surface");
  const sparse = points.length <= 60;
  const animate = !prefersReducedMotion();

  const chart = (
    <>
      <div className="section-head" style={{ marginBottom: 6 }}>
        <h2 style={{ fontSize: bare ? 18 : 22 }}>{title}</h2>
        {summary && <span className="secondary num" style={{ fontSize: 14 }}>{summary}</span>}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={points} margin={{ top: 12, right: 8, bottom: 0, left: 0 }} syncId={syncId}>
          <CartesianGrid vertical={false} stroke={grid} />
          <XAxis dataKey="x" type={xType} domain={["dataMin", "dataMax"]} tickFormatter={formatX} tick={{ fill: muted, fontSize: 12 }}
            stroke={axis} tickLine={false} minTickGap={24} />
          <YAxis tickFormatter={formatTick ?? formatY} tick={{ fill: muted, fontSize: 12 }} axisLine={false} tickLine={false} width={40}
            reversed={reversed} domain={["auto", "auto"]} />
          <Tooltip
            cursor={{ stroke: "#5b6066" }}
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
          {/* Few points (one per ride/session): straight segments with a marker each, no implied curve between them */}
          <Line type={sparse ? "linear" : "monotone"} dataKey="y" stroke={color} strokeWidth={2}
            dot={sparse ? { r: 4, fill: color, stroke: surface, strokeWidth: 2 } : false}
            activeDot={{ r: 5, stroke: surface, strokeWidth: 2 }} isAnimationActive={animate} animationDuration={1100}
            animationBegin={i != null ? 150 + i * 80 : 150} connectNulls={false} />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
  return bare ? chart : <Card i={i}>{chart}</Card>;
}
