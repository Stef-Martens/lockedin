import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { prefersReducedMotion } from "../lib/motion";
import { useCssVar } from "../lib/useCssVar";
import { Card } from "./ui";

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Europe/Brussels" });

interface Props {
  title: string;
  rows: Record<string, number | string>[];
  dataKey: string;
  colorVar: string;
  format: (v: number) => string;
  summary?: string;
  i?: number;
}

/** Single-series weekly bars (distance, volume). */
export default function WeeklyBars({ title, rows, dataKey, colorVar, format, summary, i }: Props) {
  const color = useCssVar(colorVar);
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const axis = useCssVar("--axis");
  return (
    <Card i={i}>
      <div className="section-head" style={{ marginBottom: 6 }}>
        <h2>{title}</h2>
        {summary && <span className="secondary num" style={{ fontSize: 14 }}>{summary}</span>}
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={rows} margin={{ top: 12, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={grid} />
          <XAxis dataKey="week_start" tickFormatter={shortDate} tick={{ fill: muted, fontSize: 12 }} stroke={axis} tickLine={false} minTickGap={16} />
          <YAxis tick={{ fill: muted, fontSize: 12 }} axisLine={false} tickLine={false} width={40} allowDecimals={false}
            tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${v}`)} />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} content={({ active, payload, label }) =>
            active && payload?.length ? (
              <div className="chart-tooltip num">
                <div className="muted">Week of {shortDate(String(label))}</div>
                <strong>{format(Number(payload[0].value))}</strong>
              </div>
            ) : null} />
          <Bar dataKey={dataKey} fill={color} maxBarSize={28} radius={[4, 4, 0, 0]} isAnimationActive={!prefersReducedMotion()}
            animationDuration={700} animationBegin={200} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
