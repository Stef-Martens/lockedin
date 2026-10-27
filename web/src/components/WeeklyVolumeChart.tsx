import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatMinutes, type WeekRow } from "../lib/focus";
import { dayMonth, SPORT_LABEL, type Sport } from "../lib/format";
import { prefersReducedMotion } from "../lib/motion";
import { useCssVar } from "../lib/useCssVar";
import SportDot from "./SportDot";
import { Card, Segmented } from "./ui";

const STACK: Sport[] = ["bike", "run", "swim", "gym", "other"];

/** Weekly training minutes stacked by sport; colour follows the sport, never its rank. */
export default function WeeklyVolumeChart({ rows, weeks, onWeeks, i }: {
  rows: WeekRow[]; weeks: 12 | 26; onWeeks: (w: 12 | 26) => void; i?: number;
}) {
  const [table, setTable] = useState(false);
  const colors: Record<Sport, string> = {
    bike: useCssVar("--sport-bike"), run: useCssVar("--sport-run"), swim: useCssVar("--sport-swim"),
    gym: useCssVar("--sport-gym"), other: useCssVar("--sport-other"),
  };
  const surface = useCssVar("--surface");
  const grid = useCssVar("--hairline");
  const muted = useCssVar("--ink-muted");
  const axis = useCssVar("--axis");
  const present = STACK.filter((s) => rows.some((r) => r[s] > 0));
  const shown = present.length ? present : (["bike"] as Sport[]);
  const animate = !prefersReducedMotion();

  return (
    <Card i={i}>
      <div className="section-head">
        <h2>Weekly training time</h2>
        <div className="row" style={{ gap: 16 }}>
          <div className="legend" aria-label="Legend">
            {shown.map((s) => <span key={s}><SportDot sport={s} />{SPORT_LABEL[s]}</span>)}
          </div>
          <Segmented label="Weeks" value={weeks} onChange={onWeeks} options={[{ value: 12, label: "12 wk" }, { value: 26, label: "26 wk" }]} />
        </div>
      </div>
      {table ? (
        <div className="table-wrap">
          <table className="table num">
            <thead>
              <tr><th>Week of</th>{shown.map((s) => <th key={s} className="num">{SPORT_LABEL[s]}</th>)}<th className="num">Total</th></tr>
            </thead>
            <tbody>
              {[...rows].reverse().map((r) => (
                <tr key={r.week_start}>
                  <td>{dayMonth(r.week_start)}</td>
                  {shown.map((s) => <td key={s} className="num">{r[s] ? formatMinutes(r[s]) : "–"}</td>)}
                  <td className="num">{formatMinutes(STACK.reduce((t, s) => t + r[s], 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="28%">
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis dataKey="week_start" tickFormatter={dayMonth} tick={{ fill: muted, fontSize: 12 }} stroke={axis} tickLine={false} minTickGap={16} />
            <YAxis tickFormatter={(m: number) => (m >= 60 ? `${Math.round(m / 60)}h` : `${m}`)} tick={{ fill: muted, fontSize: 12 }}
              axisLine={false} tickLine={false} width={36} allowDecimals={false} />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as WeekRow;
                return (
                  <div className="chart-tooltip num">
                    <div className="muted">Week of {dayMonth(String(label))}</div>
                    {STACK.filter((s) => row[s] > 0).map((s) => (
                      <div key={s} className="row" style={{ gap: 6 }}><SportDot sport={s} />{SPORT_LABEL[s]} {formatMinutes(row[s])}</div>
                    ))}
                    <div><strong>{formatMinutes(STACK.reduce((t, s) => t + row[s], 0))}</strong></div>
                  </div>
                );
              }}
            />
            {STACK.map((s, n) => (
              <Bar key={s} dataKey={s} stackId="t" fill={colors[s]} stroke={surface} strokeWidth={2} maxBarSize={30}
                radius={[3, 3, 0, 0]} isAnimationActive={animate} animationDuration={700} animationBegin={250 + n * 60} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
      <button className="btn ghost" style={{ paddingLeft: 0 }} onClick={() => setTable(!table)}>
        {table ? "Show chart" : "Show table"}
      </button>
    </Card>
  );
}
