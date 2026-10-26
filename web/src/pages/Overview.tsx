import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import FocusCard from "../components/FocusCard";
import { Card, PageHeader, SectionHead, Segmented } from "../components/ui";
import WeeklyVolumeChart from "../components/WeeklyVolumeChart";
import WinsStrip from "../components/WinsStrip";
import type { AgendaItem, AgendaWeek } from "../lib/agenda";
import { apiFetch } from "../lib/api";
import { formatMinutes, type Overview as OverviewData } from "../lib/focus";
import { formatDistance, SPORT_LABEL, type Sport } from "../lib/format";
import { shiftWeek } from "../lib/musclemap";
import { stagger, useCountUp } from "../lib/motion";

const SPORTS: Sport[] = ["bike", "run", "swim", "gym", "other"];
const TREND: Partial<Record<Sport, string>> = { bike: "/trends/bike", run: "/trends/run", swim: "/trends/swim", gym: "/trends/gym" };

function isoWeek(d: Date): number {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  return Math.ceil(((t.getTime() - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
}

function ago(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 864e5);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

const dayMonth = (d: string) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

function checkinText(d: OverviewData): string {
  if (!d.last_checkin_on) return "No measurements yet; two minutes with a tape measure.";
  if (!d.checkin_due) return `Next one on ${dayMonth(d.next_checkin_on)}.`;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Brussels" });
  return d.next_checkin_on === today ? "Due today." : `Was due on ${dayMonth(d.next_checkin_on)}.`;
}

function TotalTile({ minutes, sessions, label }: { minutes: number; sessions: number; label: string }) {
  const shown = useCountUp(minutes);
  return (
    <div className="card rise" style={stagger(0)}>
      <div className="eyebrow">{label}</div>
      <div className="display num" style={{ fontSize: 64, marginTop: 8 }}>{formatMinutes(shown)}</div>
      <div className="secondary" style={{ fontSize: 14, marginTop: 6 }}>{sessions} {sessions === 1 ? "session" : "sessions"}</div>
    </div>
  );
}

type Goal = { id: number; text: string; target: string | null; progress?: GoalProgress };

type GoalProgress = { label: string; fraction: number } | null;

// Rest days and notes can't be ticked off, so they don't count as to-dos.
const trackable = (i: AgendaItem) => !["rest", "other"].includes(i.sport);

function TodayBlock({ items, upcoming }: { items: AgendaItem[] | "failed"; upcoming: AgendaItem[] }) {
  if (items === "failed") {
    return (
      <Card variant="accent" i={0}>
        <SectionHead title="Today" />
        <p className="secondary" style={{ margin: 0 }}>Couldn't load today's plan. <Link to="/agenda">Open the agenda</Link></p>
      </Card>
    );
  }
  const todo = items.filter(trackable);
  const done = todo.filter((i) => i.done).length;
  const next = upcoming.length
    ? `${new Date(`${upcoming[0].day}T12:00`).toLocaleDateString("en-GB", { weekday: "long" })}: ${upcoming.map((u) => u.title + (u.optional ? " (optional)" : "")).join(", ")}`
    : null;
  return (
    <Card variant="accent" i={0}>
      <SectionHead title="Today" right={todo.length ? <span className="secondary" style={{ fontSize: 13 }}>{done} of {todo.length} done</span> : undefined} />
      {items.length === 0 && <p className="secondary" style={{ margin: 0 }}>Nothing planned today. <Link to="/agenda">Open the agenda</Link></p>}
      {items.map((it) => (
        <div key={it.id} className={`today-row${it.done ? " done" : ""}`}>
          {trackable(it) ? <span className={`today-check${it.done ? " done pop" : ""}`} aria-hidden="true">{it.done ? "✓" : ""}</span>
            : <span className="today-check note" aria-hidden="true" />}
          <div style={{ minWidth: 0 }}>
            <div className="today-title">{it.title}{it.goal && <span className="goal-tag">for: {it.goal}</span>}{it.optional && <span className="muted"> · optional</span>}</div>
            <div className="secondary" style={{ fontSize: 13 }}>{it.done ? it.result : it.zwift?.summary ?? it.note ?? (it.routine ? "Your routine" : "")}</div>
          </div>
          {it.done ? <Link className="btn small" style={{ textDecoration: "none" }} to={`/agenda/${it.id}`}>See how it went</Link>
            : it.sport === "gym" && it.routine ? <Link className="btn primary small" style={{ textDecoration: "none" }} to={`/plan?day=${encodeURIComponent(it.routine)}`}>Plan it</Link>
            : <Link className="btn small" style={{ textDecoration: "none" }} to={`/agenda/${it.id}`}>Open</Link>}
        </div>
      ))}
      {next && <div className="secondary" style={{ fontSize: 13, marginTop: 10 }}>Next · {next}</div>}
    </Card>
  );
}

function GymCards({ goals, goalsFailed }: { goals: Goal[] | null; goalsFailed: boolean }) {
  return (
    <div className="grid-auto" style={{ ["--min" as string]: "300px" }}>
      <Link to="/plan" className="card accent lift rise" style={{ ...stagger(1), display: "block", color: "var(--ink)", textDecoration: "none" }}>
        <div className="eyebrow">Going to the gym?</div>
        <div className="row spread" style={{ marginTop: 8 }}>
          <span style={{ fontSize: 15, color: "var(--ink-2)" }}>Your routine with today's targets and what you've missed.</span>
          <span className="btn primary" style={{ whiteSpace: "nowrap" }}>Plan a workout</span>
        </div>
      </Link>
      <div className="card rise" style={stagger(2)}>
        <div className="row spread">
          <span className="eyebrow">Your goals</span>
          <Link to="/coach" style={{ fontSize: 13, fontWeight: 600, textDecoration: "none" }}>Coach</Link>
        </div>
        {goalsFailed ? (
          <p className="muted" style={{ margin: "8px 0 0", fontSize: 14 }}>Couldn't load your goals.</p>
        ) : goals && goals.length > 0 ? (
          <div style={{ marginTop: 6 }}>
            {goals.map((g) => (
              <div key={g.id} className="goal-progress">
                <div className="row spread" style={{ flexWrap: "nowrap" }}>
                  <span>{g.text}</span>
                  {g.progress && <span className="secondary num" style={{ fontSize: 13, whiteSpace: "nowrap" }}>{g.progress.label}</span>}
                </div>
                {g.progress && <div className="goal-bar"><span className="grow-x" style={{ width: `${Math.round(g.progress.fraction * 100)}%` }} /></div>}
                {g.target && <div className="muted" style={{ fontSize: 12 }}>{g.target}</div>}
              </div>
            ))}
          </div>
        ) : goals ? (
          <p className="muted" style={{ margin: "8px 0 0", fontSize: 14 }}>No goals yet. Set some with the coach.</p>
        ) : null}
      </div>
    </div>
  );
}

export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [weeks, setWeeks] = useState<12 | 26>(12);
  const [period, setPeriod] = useState<"week" | "month">("week");
  const [error, setError] = useState<string | null>(null);
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [goalsFailed, setGoalsFailed] = useState(false);
  const [today, setToday] = useState<AgendaItem[] | "failed" | null>(null);
  const [upcoming, setUpcoming] = useState<AgendaItem[]>([]);

  useEffect(() => {
    apiFetch<Goal[]>("/api/goals/active").then(setGoals).catch(() => setGoalsFailed(true));
    const firstDay = (items: AgendaItem[], after: string) => {
      const later = items.filter((i) => i.day > after);
      return later.filter((i) => i.day === later[0]?.day);
    };
    apiFetch<AgendaWeek>("/api/agenda").then((w) => {
      setToday(w.items.filter((i) => i.day === w.today));
      const next = firstDay(w.items, w.today);
      if (next.length) setUpcoming(next);
      else {  // nothing left this week (always so on a Sunday): look at the next one
        apiFetch<AgendaWeek>(`/api/agenda?week=${shiftWeek(w.week_start, 1)}`)
          .then((n) => setUpcoming(firstDay(n.items, w.today))).catch(() => undefined);
      }
    }).catch(() => setToday("failed"));
  }, []);

  useEffect(() => {
    apiFetch<OverviewData>(`/api/overview?weeks=${weeks}`).then(setData).catch((e) => setError(e.message));
  }, [weeks]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  const t = data.totals[period];
  const active = SPORTS.filter((s) => t[s].sessions > 0);
  const total = SPORTS.reduce((m, s) => m + t[s].time_s / 60, 0);
  const sessions = SPORTS.reduce((n, s) => n + t[s].sessions, 0);
  const c = data.comeback;
  const now = new Date();
  const eyebrow = `${now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "Europe/Brussels" })} · week ${isoWeek(now)}`;
  const monthName = now.toLocaleDateString("en-GB", { month: "long", timeZone: "Europe/Brussels" });

  return (
    <>
      <PageHeader eyebrow={eyebrow} title={!c ? "Overview" : c.days_since == null ? "Welcome" : "Welcome back"}
        right={<Segmented label="Period" value={period} onChange={setPeriod}
          options={[{ value: "week", label: "Week" }, { value: "month", label: "Month" }]} />} />

      {c && (
        <Card variant="accent" i={0}>
          {c.days_since == null ? (
            <p style={{ margin: 0 }}>Nothing logged yet. Your Zwift rides and Watch workouts appear once the Mac sync runs, or{" "}
              <Link to="/import">import a Hevy export</Link>. Suggestions show up after a couple of weeks of training.</p>
          ) : (
            <p style={{ margin: 0 }}>Last session {c.days_since} days ago. {c.suggestion}</p>
          )}
        </Card>
      )}

      {today && <TodayBlock items={today} upcoming={upcoming} />}
      <GymCards goals={goals} goalsFailed={goalsFailed} />

      <div className="grid-auto" style={{ ["--min" as string]: "200px" }}>
        <TotalTile key={period} minutes={Math.round(total)} sessions={sessions} label={period === "week" ? "This week" : monthName} />
        {active.map((s, n) => {
          const body = (
            <>
              <div className="eyebrow row" style={{ gap: 8 }}><span className="dot" style={{ background: `var(--sport-${s})` }} />{SPORT_LABEL[s]}</div>
              <div className="display num" style={{ fontSize: 44, marginTop: 14 }}>{formatMinutes(t[s].time_s / 60)}</div>
              <div className="secondary" style={{ fontSize: 14, marginTop: 6 }}>
                {t[s].sessions} {t[s].sessions === 1 ? "session" : "sessions"}
                {t[s].distance_m > 0 && s !== "gym" ? ` · ${formatDistance(t[s].distance_m, s)}` : ""}
              </div>
            </>
          );
          return TREND[s] ? (
            <Link key={s} to={TREND[s]!} className="card rise lift" style={{ ...stagger(n + 1), display: "block", color: "var(--ink)", textDecoration: "none" }}>{body}</Link>
          ) : (
            <div key={s} className="card rise" style={stagger(n + 1)}>{body}</div>
          );
        })}
        {data.streak >= 2 && (
          <div className="card rise" style={stagger(active.length + 1)}>
            <div className="eyebrow">Streak</div>
            <div className="row" style={{ gap: 8, marginTop: 14, alignItems: "baseline" }}>
              <span className="display" style={{ fontSize: 44, color: "var(--accent)" }}>{data.streak}</span>
              <span style={{ color: "var(--ink-2)" }}>weeks</span>
            </div>
            <div className="secondary" style={{ fontSize: 14, marginTop: 6 }}>2+ sessions every week</div>
          </div>
        )}
      </div>

      {(!c || data.wins.length > 0) && (
        <div className="grid-auto" style={{ ["--min" as string]: "340px" }}>
          {!c && <FocusCard items={data.focus} i={2} />}
          <WinsStrip wins={data.wins} i={3} />
        </div>
      )}

      {data.plateaus.length > 0 && (
        <Card i={4}>
          <SectionHead title="Stalled lately" />
          {data.plateaus.map((p, n) => (
            <div key={n} style={{ padding: "10px 0", borderTop: n ? "1px solid var(--hairline)" : undefined }}>
              <div className="list-title">{p.title}</div>
              <div className="muted num" style={{ fontSize: 13 }}>{p.detail}</div>
              <div style={{ color: "var(--ink-2)", marginTop: 2 }}>{p.suggestion}</div>
            </div>
          ))}
        </Card>
      )}

      <WeeklyVolumeChart rows={data.weekly} weeks={weeks} onWeeks={setWeeks} i={5} />

      <div className="grid-auto rise" style={{ ["--min" as string]: "320px", ...stagger(6) }}>
        <Link to="/body" className={`note lift ${data.checkin_due ? "accent" : ""}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, textDecoration: "none", color: "var(--ink-2)" }}>
          <span className="row" style={{ gap: 12, flexWrap: "nowrap" }}>
            {data.checkin_due && <span className="sync-dot live pulse" aria-hidden="true" />}
            <span>
              <strong style={{ color: "var(--ink)" }}>{data.checkin_due ? "Body check-in due." : "Body check-in up to date."}</strong>{" "}
              {checkinText(data)}
            </span>
          </span>
          <span style={{ color: "var(--accent)", fontWeight: 600, whiteSpace: "nowrap" }}>{data.checkin_due ? "Check in" : "Open"}</span>
        </Link>
        <Link to="/import" className={`note lift ${data.hevy_due ? "accent" : ""}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, textDecoration: "none", color: "var(--ink-2)" }}>
          <span>
            <strong style={{ color: "var(--ink)" }}>Hevy</strong>{" "}
            {data.hevy_last_upload_at ? `last uploaded ${ago(data.hevy_last_upload_at)}.` : "not uploaded yet."}{" "}
            {data.hevy_due ? "Upload your latest export to keep gym suggestions current." : ""}
          </span>
          <span style={{ color: "var(--accent)", fontWeight: 600, whiteSpace: "nowrap" }}>Upload</span>
        </Link>
      </div>
    </>
  );
}
