import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCssVar } from "../lib/useCssVar";

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Europe/Brussels" });

interface Props {
  title: string;
  rows: Record<string, number | string>[];
  dataKey: string;
  colorVar: string;
  format: (v: number) => string;
  summary?: string;
}

/** Single-series weekly bars (distance, volume). */
export default function WeeklyBars({ title, rows, dataKey, colorVar, format, summary }: Props) {
  const color = useCssVar(colorVar);
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const axis = useCssVar("--axis");
  return (
    <section className="card">
      <div className="chart-title">
        <h2>{title}</h2>
        {summary && <span className="secondary num">{summary}</span>}
      </div>
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={rows} margin={{ top: 12, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={grid} />
          <XAxis dataKey="week_start" tickFormatter={shortDate} tick={{ fill: muted, fontSize: 12 }} stroke={axis}
            tickLine={false} minTickGap={16} />
          <YAxis tick={{ fill: muted, fontSize: 12 }} axisLine={false} tickLine={false} width={40} allowDecimals={false}
            tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${v}`)} />
          <Tooltip cursor={{ fill: "var(--wash)" }} content={({ active, payload, label }) =>
            active && payload?.length ? (
              <div className="chart-tooltip num">
                <div className="muted">Week of {shortDate(String(label))}</div>
                <strong>{format(Number(payload[0].value))}</strong>
              </div>
            ) : null} />
          <Bar dataKey={dataKey} fill={color} maxBarSize={24} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
