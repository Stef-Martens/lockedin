import SeriesChart from "../../components/SeriesChart";
import WeeklyBars from "../../components/WeeklyBars";
import type { EffortMix } from "../../lib/focus";
import { dayMonth, formatDuration, formatPace } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import { Empty, Failed, MixBar, pts, TryThis, useFocusSessions } from "./shared";

interface RunData { runs: { date: string; pace_s_per_km: number | null; aerobic_efficiency: number | null }[]; weekly: { week_start: string; km: number }[]; mix: EffortMix }

export default function Run() {
  const { data: d, error, reload } = useApi<RunData>("/api/trends/run");
  const sugg = useFocusSessions();
  if (error) return <Failed retry={reload} />;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.runs.length) return <Empty what="runs" charts={["Pace per run", "Aerobic efficiency", "Weekly distance"]} />;
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "300px" }}>
        <MixBar mix={d.mix} i={1} />
        <TryThis items={sugg} sport="run" i={2} />
      </div>
      <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
        <SeriesChart title="Pace per run" points={pts(d.runs, (r) => r.date, (r) => r.pace_s_per_km)} colorVar="--series-pace" reversed
          formatX={dayMonth} formatY={formatPace} formatTick={formatDuration} i={3} />
        <SeriesChart title="Aerobic efficiency" summary="higher = fitter" points={pts(d.runs, (r) => r.date, (r) => r.aerobic_efficiency)}
          colorVar="--series-cadence" formatX={dayMonth} formatY={(y) => y.toFixed(2)} i={4} />
      </div>
      <WeeklyBars title="Weekly distance" rows={d.weekly} dataKey="km" colorVar="--sport-run" format={(v) => `${v} km`} i={5} />
    </>
  );
}
