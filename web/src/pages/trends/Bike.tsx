import { Link } from "react-router-dom";
import SeriesChart from "../../components/SeriesChart";
import type { EffortMix } from "../../lib/focus";
import { dayMonth } from "../../lib/format";
import { stagger } from "../../lib/motion";
import type { Profile } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { Empty, Failed, MixBar, pts, TryThis, useFocusSessions } from "./shared";

interface BikeData { rides: { date: string; np: number | null; efficiency: number | null; best_20m: number | null }[]; ftp: number | null; mix: EffortMix }

export default function Bike() {
  const { data: d, error, reload } = useApi<BikeData>("/api/trends/bike");
  const { data: profile } = useApi<Profile>("/api/profile");
  const sugg = useFocusSessions();
  if (error) return <Failed retry={reload} />;
  if (!d) return <p className="muted">Loading…</p>;
  if (!d.rides.length) return <Empty what="rides" charts={["Normalized power", "Efficiency", "Best 20-min power"]} />;
  const bests = d.rides.map((r) => r.best_20m ?? 0);
  const best = Math.max(...bests);
  const before = Math.max(0, ...bests.slice(0, bests.lastIndexOf(best)));
  return (
    <>
      <div className="grid-auto" style={{ ["--min" as string]: "240px" }}>
        <div className="card rise" style={stagger(1)}>
          <div className="eyebrow">FTP · {profile?.ftp_override ? "yours" : "estimated"}</div>
          <div className="display num big-stat">{profile?.ftp_override ?? (d.ftp ? Math.round(d.ftp) : "–")} W</div>
          {!profile?.ftp_override && <div className="secondary" style={{ fontSize: 13, marginTop: 6 }}>95% of your best 20 min. <Link to="/body" style={{ textDecoration: "none" }}>Set your Zwift FTP</Link></div>}
        </div>
        <div className="card rise" style={stagger(2)}>
          <div className="eyebrow">Best 20-min power</div>
          <div className="row" style={{ gap: 10, marginTop: 10, alignItems: "baseline" }}>
            <span className="display num" style={{ fontSize: 48, color: "var(--accent)" }}>{Math.round(best)} W</span>
            {before > 0 && best > before && <span className="secondary" style={{ fontSize: 14 }}>+{Math.round(best - before)} W vs previous best</span>}
          </div>
        </div>
        <MixBar mix={d.mix} i={3} />
      </div>
      <TryThis items={sugg} sport="bike" i={4} />
      <div className="grid-auto" style={{ ["--min" as string]: "440px" }}>
        <SeriesChart title="Normalized power" summary="per ride" points={pts(d.rides, (r) => r.date, (r) => r.np)} colorVar="--series-power"
          formatX={dayMonth} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} i={5} />
        <SeriesChart title="Efficiency" summary="power ÷ heart rate · higher = fitter" points={pts(d.rides, (r) => r.date, (r) => r.efficiency)}
          colorVar="--series-cadence" formatX={dayMonth} formatY={(y) => y.toFixed(2)} i={6} />
        <SeriesChart title="Best 20-min power" summary="per ride" points={pts(d.rides, (r) => r.date, (r) => r.best_20m)} colorVar="--series-body"
          formatX={dayMonth} formatY={(y) => `${Math.round(y)} W`} formatTick={(y) => `${Math.round(y)}`} i={7} />
      </div>
    </>
  );
}
