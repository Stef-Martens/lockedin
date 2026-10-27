import SeriesChart from "../../components/SeriesChart";
import WeeklyBars from "../../components/WeeklyBars";
import { dayMonth, formatDuration, formatSwimPace } from "../../lib/format";
import { useApi } from "../../lib/useApi";
import { Empty, Failed, pts } from "./shared";

interface SwimData { swims: { date: string; pace_s_per_100m: number | null }[]; weekly: { week_start: string; m: number }[] }

export default function Swim() {
  const { data: d, error, reload } = useApi<SwimData>("/api/trends/swim");
  if (error) return <Failed retry={reload} />;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.swims.length) return <Empty what="swims" charts={["Weekly distance", "Pace per 100 m"]} />;
  return (
    <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
      <WeeklyBars title="Weekly distance" rows={d.weekly} dataKey="m" colorVar="--sport-swim" format={(v) => `${v} m`} i={1} />
      <SeriesChart title="Pace per 100 m" points={pts(d.swims, (r) => r.date, (r) => r.pace_s_per_100m)} colorVar="--sport-swim" reversed
        formatX={dayMonth} formatY={formatSwimPace} formatTick={formatDuration} i={2} />
    </div>
  );
}
