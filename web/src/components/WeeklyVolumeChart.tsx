import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatMinutes, type WeekRow } from "../lib/focus";
import { SPORT_LABEL, type Sport } from "../lib/format";
import { useCssVar } from "../lib/useCssVar";
import SportDot from "./SportDot";

const STACK: Sport[] = ["bike", "run", "swim", "gym", "other"];
const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Europe/Brussels" });

interface Props {
  rows: WeekRow[];
  weeks: 12 | 26;
  onWeeks: (w: 12 | 26) => void;
}

/** Weekly training minutes stacked by sport; colour follows the sport, never its rank. */
export default function WeeklyVolumeChart({ rows, weeks, onWeeks }: Props) {
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

  return (
    <section className="card">
      <div className="chart-title">
        <h2>Weekly training time</h2>
        <div className="row" style={{ gap: 6 }}>
          {([12, 26] as const).map((w) => (
            <button key={w} className="chip" aria-pressed={weeks === w} onClick={() => onWeeks(w)}>{w} wk</button>
          ))}
        </div>
      </div>
      <div className="row" style={{ gap: 14, margin: "4px 0 8px", fontSize: "0.85rem" }} aria-label="Legend">
        {shown.map((s) => (
          <span key={s} className="row secondary" style={{ gap: 6 }}><SportDot sport={s} />{SPORT_LABEL[s]}</span>
        ))}
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
                  <td>{shortDate(r.week_start)}</td>
                  {shown.map((s) => <td key={s} className="num">{r[s] ? formatMinutes(r[s]) : "–"}</td>)}
                  <td className="num">{formatMinutes(STACK.reduce((t, s) => t + r[s], 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="25%">
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis dataKey="week_start" tickFormatter={shortDate} tick={{ fill: muted, fontSize: 12 }} stroke={axis}
              tickLine={false} minTickGap={16} />
            <YAxis tickFormatter={(m: number) => (m >= 60 ? `${Math.round(m / 60)}h` : `${m}`)} tick={{ fill: muted, fontSize: 12 }}
              axisLine={false} tickLine={false} width={36} allowDecimals={false} />
            <Tooltip
              cursor={{ fill: "var(--wash)" }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as WeekRow;
                const total = STACK.reduce((t, s) => t + row[s], 0);
                return (
                  <div className="chart-tooltip num">
                    <div className="muted">Week of {shortDate(String(label))}</div>
                    {STACK.filter((s) => row[s] > 0).map((s) => (
                      <div key={s} className="row" style={{ gap: 6 }}><SportDot sport={s} />{SPORT_LABEL[s]} {formatMinutes(row[s])}</div>
                    ))}
                    <div><strong>{formatMinutes(total)}</strong></div>
                  </div>
                );
              }}
            />
            {STACK.map((s) => (
              <Bar key={s} dataKey={s} stackId="t" fill={colors[s]} stroke={surface} strokeWidth={2} maxBarSize={24}
                radius={[3, 3, 0, 0]} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
      <button className="btn ghost" style={{ padding: "4px 0", marginTop: 4 }} onClick={() => setTable(!table)}>
        {table ? "Show chart" : "Show table"}
      </button>
    </section>
  );
}
