import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import FocusCard from "../components/FocusCard";
import SportDot from "../components/SportDot";
import WeeklyVolumeChart from "../components/WeeklyVolumeChart";
import WinsStrip from "../components/WinsStrip";
import { apiFetch } from "../lib/api";
import { formatMinutes, type Overview as OverviewData } from "../lib/focus";
import { formatDistance, SPORT_LABEL, type Sport } from "../lib/format";

const SPORTS: Sport[] = ["bike", "run", "swim", "gym", "other"];

export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [weeks, setWeeks] = useState<12 | 26>(12);
  const [period, setPeriod] = useState<"week" | "month">("week");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<OverviewData>(`/api/overview?weeks=${weeks}`).then(setData).catch((e) => setError(e.message));
  }, [weeks]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  const t = data.totals[period];
  const active = SPORTS.filter((s) => t[s].sessions > 0);
  const c = data.comeback;

  return (
    <>
      <h1>{!c ? "Overview" : c.days_since == null ? "Welcome" : "Welcome back"}</h1>
      {c && (
        <section className="card note-card">
          {c.days_since == null ? (
            <p style={{ margin: 0 }}>
              Nothing logged yet. Your Zwift rides and Watch workouts appear once the Mac sync runs, or{" "}
              <Link to="/import">import a Hevy export</Link>. Suggestions show up after a couple of weeks of training.
            </p>
          ) : (
            <p style={{ margin: 0 }}>Last session {c.days_since} days ago. {c.suggestion}</p>
          )}
        </section>
      )}

      {!c && <FocusCard items={data.focus} />}
      <WinsStrip wins={data.wins} />
      {data.plateaus.length > 0 && (
        <section className="card">
          <h2>Stalled lately</h2>
          {data.plateaus.map((p, i) => (
            <div key={i} className="plateau">
              <div className="list-title">{p.title}</div>
              <div className="muted num" style={{ fontSize: "0.85rem" }}>{p.detail}</div>
              <div>{p.suggestion}</div>
            </div>
          ))}
        </section>
      )}

      <section className="card">
        <div className="chart-title">
          <h2>{period === "week" ? "This week" : "This month"}</h2>
          <div className="row" style={{ gap: 6 }}>
            <button className="chip" aria-pressed={period === "week"} onClick={() => setPeriod("week")}>Week</button>
            <button className="chip" aria-pressed={period === "month"} onClick={() => setPeriod("month")}>Month</button>
          </div>
        </div>
        <div className="tiles" style={{ marginBottom: 0, marginTop: 8 }}>
          {active.map((s) => (
            <div className="tile" key={s}>
              <div className="label row" style={{ gap: 6 }}><SportDot sport={s} />{SPORT_LABEL[s]}</div>
              <div className="value num">{formatMinutes(t[s].time_s / 60)}</div>
              <div className="muted num" style={{ fontSize: "0.85rem" }}>
                {t[s].sessions} {t[s].sessions === 1 ? "session" : "sessions"}
                {t[s].distance_m > 0 && s !== "gym" ? ` · ${formatDistance(t[s].distance_m, s)}` : ""}
              </div>
            </div>
          ))}
          {data.streak >= 2 && (
            <div className="tile">
              <div className="label">Streak</div>
              <div className="value num">{data.streak} weeks</div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>2+ sessions a week</div>
            </div>
          )}
          {active.length === 0 && <p className="secondary" style={{ margin: 0 }}>Nothing yet {period === "week" ? "this week" : "this month"}.</p>}
        </div>
      </section>

      <WeeklyVolumeChart rows={data.weekly} weeks={weeks} onWeeks={setWeeks} />

      {data.measure_due && (
        <p className="note">
          {data.last_tape_measurement_on ? "It's been a while since you measured. " : "No body measurements yet. "}
          <Link to="/body">Time to measure</Link>: chest, arms, waist and thighs take two minutes.
        </p>
      )}
    </>
  );
}
