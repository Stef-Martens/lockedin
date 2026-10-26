import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, SectionHead } from "../components/ui";
import { apiFetch } from "../lib/api";
import { SPORT_NAME, type AgendaItem } from "../lib/agenda";
import { stagger } from "../lib/motion";
import { changeLabel, doseLine, type PlanItem } from "../lib/plan";
import { mmss, paceText, statusLabel, type Part, type SessionActual, type SessionDetail, type SessionPlan, type Status } from "../lib/session";

const dayText = (iso: string) => new Date(`${iso}T12:00`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
const minutes = (s: number | null | undefined) => (s == null ? "–" : `${Math.round(s / 60)}′`);

function StatusText({ status }: { status: Status }) {
  const s = statusLabel(status);
  return <span className={`status-${s.tone}`}>{s.text}</span>;
}

function Tile({ label, value, sub, i }: { label: string; value: string; sub?: string; i: number }) {
  return (
    <div className="tile rise" style={stagger(i, 0.04)}>
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
      {sub && <div className="hint">{sub}</div>}
    </div>
  );
}

type Tick = { at: number; text: string };

/** Minute marks every 5, 10, 20, 30 or 60 minutes: whichever keeps it to about seven. */
function timeTicks(end: number): Tick[] {
  const step = [300, 600, 1200, 1800, 3600].find((s) => end / s <= 7) ?? 7200;
  return Array.from({ length: Math.floor(end / step) + 1 }, (_, m) => ({ at: (m * step) / end, text: `${(m * step) / 60}′` }))
    .filter((t) => t.at <= 0.96);
}

/** Pointer position over the chart as seconds into the session. */
function useHoverTime(end: number) {
  const [t, setT] = useState<number | null>(null);
  const handlers = {
    onPointerMove: (e: React.PointerEvent<SVGSVGElement>) => {
      const box = e.currentTarget.getBoundingClientRect();
      if (box.width > 0) setT(Math.max(0, Math.min(end, ((e.clientX - box.left) / box.width) * end)));
    },
    onPointerLeave: () => setT(null),
  };
  return [t, handlers] as const;
}

const nearest = (pts: [number, number][], t: number) =>
  pts.reduce<[number, number] | null>((best, p) => (!best || Math.abs(p[0] - t) < Math.abs(best[0] - t) ? p : best), null);

/** A chart whose value and time labels are HTML, so they stay readable however narrow the chart gets.
 * `ticks` are in the SVG's own units (0 at the top, `height` at the bottom). */
function ChartFrame({ label, height, ticks, times, readout, children }: {
  label: string; height: number; ticks: Tick[]; times: Tick[]; readout?: string | null; children: React.ReactNode;
}) {
  return (
    <div className="chart-frame" role="group" aria-label={label}>
      <div className="chart-axis" aria-hidden="true">
        {ticks.map((t) => <span key={t.text} style={{ top: `${(t.at / height) * 100}%` }}>{t.text}</span>)}
      </div>
      <div className="chart-plot">
        {children}
        {readout && <div className="chart-readout num" role="status">{readout}</div>}
      </div>
      <div className="chart-times" aria-hidden="true">
        {times.map((t) => <span key={t.text} style={{ left: `${t.at * 100}%` }}>{t.text}</span>)}
      </div>
    </div>
  );
}

/** The planned blocks: bars sized by time and power, with the FTP as a dashed line. */
function PlanChart({ parts }: { parts: Part[] }) {
  const end = parts[parts.length - 1]?.end_s || 1;
  const top = Math.max(1.1, ...parts.map((p) => Math.max(p.from_frac, p.to_frac))) * 1.05;
  const y = (f: number) => 165 - (f / top) * 160;
  return (
    <ChartFrame label="Workout shape" height={165} ticks={[{ at: y(1), text: "FTP" }, { at: y(0.5), text: "50%" }]} times={timeTicks(end)}>
      <svg className="session-chart" style={{ ["--chart-h" as string]: "150px" }} viewBox="0 0 640 165" preserveAspectRatio="none" role="img" aria-label="Workout shape">
        {parts.map((p, n) => (
          <polygon key={n} className={p.work ? "work" : "easy"}
            points={`${(p.start_s / end) * 640},165 ${(p.start_s / end) * 640},${y(p.from_frac)} ${(p.end_s / end) * 640},${y(p.to_frac)} ${(p.end_s / end) * 640},165`} />
        ))}
        <line x1="0" x2="640" y1={y(1)} y2={y(1)} className="ftp-line" />
      </svg>
    </ChartFrame>
  );
}

/** The ride: power (blue) against the planned target (dashed lime), heart rate (red), work parts shaded. */
function RideChart({ parts, a, ftp }: { parts: Part[]; a: SessionActual; ftp: number | null }) {
  const power = a.power ?? [];
  const hr = a.hr ?? [];
  const end = Math.max(parts[parts.length - 1]?.end_s ?? 0, power[power.length - 1]?.[0] ?? 0, 1);
  const maxW = Math.max(...power.map((p) => p[1]), ...parts.map((p) => Math.max(p.from_w ?? 0, p.to_w ?? 0)), (ftp ?? 0) * 1.1, 100) * 1.05;
  const [hover, handlers] = useHoverTime(end);
  const x = (t: number) => (t / end) * 1000;
  const yw = (w: number) => 200 - (w / maxW) * 195;
  const yh = (b: number) => 200 - ((b - 60) / 140) * 195;
  const line = (pts: [number, number][], y: (v: number) => number) => pts.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const target = parts.flatMap((p) => p.from_w == null ? [] : [[p.start_s, p.from_w], [p.end_s, p.to_w ?? p.from_w]] as [number, number][]);
  const step = maxW > 500 ? 100 : 50;
  const ticks = Array.from({ length: Math.floor(maxW / step) }, (_, k) => (k + 1) * step).map((w) => ({ at: yw(w), text: `${w} W` }));
  let readout: string | null = null;
  if (hover != null) {
    const w = nearest(power, hover);
    const part = parts.find((p) => p.start_s <= hover && hover < p.end_s);
    const tw = part?.from_w != null ? Math.round(part.from_w + ((part.to_w ?? part.from_w) - part.from_w) * (hover - part.start_s) / (part.end_s - part.start_s)) : null;
    readout = `${mmss(hover)}${w ? ` · ${Math.round(w[1])} W` : ""}${tw != null ? ` · target ${tw} W` : ""}`;
  }
  return (
    <ChartFrame label="Power over the ride" height={200} ticks={ticks} times={timeTicks(end)} readout={readout}>
      <svg className="session-chart" style={{ ["--chart-h" as string]: "200px" }} viewBox="0 0 1000 200" preserveAspectRatio="none"
        role="img" aria-label="Your power against the planned target" {...handlers}>
        {parts.filter((p) => p.work).map((p, n) => <rect key={n} x={x(p.start_s)} y="0" width={x(p.end_s) - x(p.start_s)} height="200" className="work-band" />)}
        {target.length > 0 && <polyline points={line(target, yw)} className="target-line" />}
        {power.length > 0 && <polyline points={line(power, yw)} className="power-line" />}
        {hr.length > 0 && <polyline points={line(hr, yh)} className="hr-line" />}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1="0" y2="200" className="cursor" />}
      </svg>
    </ChartFrame>
  );
}

/** Pace over the run (faster is higher) with the target band. */
function PaceChart({ a, low, high }: { a: SessionActual; low?: number; high?: number }) {
  const pace = (a.pace ?? []).filter((p) => p[1] < 900);
  const end = pace[pace.length - 1]?.[0] || 1;
  const [hover, handlers] = useHoverTime(end);
  if (!pace.length) return null;
  const values = pace.map((p) => p[1]).concat(low ?? [], high ?? []);
  const fast = Math.min(...values) - 10, slow = Math.max(...values) + 10;
  const y = (v: number) => ((v - fast) / (slow - fast)) * 180 + 5;
  const marks = low && high ? [low, high] : [fast + 10, slow - 10];
  const p = hover != null ? nearest(pace, hover) : null;
  return (
    <ChartFrame label="Pace over the run" height={190} ticks={marks.map((v) => ({ at: y(v), text: mmss(v) }))} times={timeTicks(end)}
      readout={hover != null && p ? `${mmss(hover)} · ${mmss(p[1])}/km` : null}>
      <svg className="session-chart" style={{ ["--chart-h" as string]: "180px" }} viewBox="0 0 1000 190" preserveAspectRatio="none"
        role="img" aria-label="Pace over the run" {...handlers}>
        {low && high && <rect x="0" width="1000" y={y(low)} height={Math.max(2, y(high) - y(low))} className="pace-band" />}
        <polyline points={pace.map(([t, v]) => `${((t / end) * 1000).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} className="pace-line" />
        {hover != null && <line x1={(hover / end) * 1000} x2={(hover / end) * 1000} y1="0" y2="190" className="cursor" />}
      </svg>
    </ChartFrame>
  );
}

function Edit({ item, onSaved, onCancel }: { item: AgendaItem; onSaved: () => void; onCancel: () => void }) {
  const t = item.targets ?? {};
  const toClock = (s?: number) => (s ? mmss(s) : "");
  const fromClock = (v: string) => { const [m, s] = v.split(":").map(Number); return v ? m * 60 + (s || 0) : undefined; };
  // Phones with a Dutch/Belgian keyboard type "8,5".
  const num = (v: string) => Number(v.replace(",", "."));
  const sameTargets = (a: object, b: object) => {
    const norm = (o: object) => JSON.stringify(Object.entries(o).filter(([, v]) => v != null).sort(([x], [y]) => x.localeCompare(y)));
    return norm(a) === norm(b);
  };
  const [form, setForm] = useState({
    title: item.title, note: item.note ?? "", day: item.day, optional: item.optional,
    distance: t.distance_m ? String(t.distance_m / 1000) : "", duration: t.duration_s ? String(Math.round(t.duration_s / 60)) : "",
    low: toClock(t.pace_low), high: toClock(t.pace_high), zone: t.hr_zone ? String(t.hr_zone) : "",
  });
  const [error, setError] = useState<string | null>(null);
  const withTargets = item.sport === "run" || item.sport === "swim";
  const save = (e: FormEvent) => {
    e.preventDefault();
    const changes: Record<string, unknown> = {};
    if (form.title !== item.title) changes.title = form.title;
    if (form.note !== (item.note ?? "")) changes.note = form.note || null;
    if (form.day !== item.day) changes.day = form.day;
    if (form.optional !== item.optional) changes.optional = form.optional;
    if (withTargets) {
      const values = [form.distance, form.duration].filter(Boolean).map(num);
      const clocks = [form.low, form.high].filter(Boolean);
      if (values.some((v) => !Number.isFinite(v)) || clocks.some((c) => !/^\d{1,2}:\d{2}$/.test(c.trim()))) {
        setError("Use numbers for distance and minutes, and m:ss for paces (e.g. 5:35).");
        return;
      }
      const next = {
        distance_m: form.distance ? Math.round(num(form.distance) * 1000) : undefined,
        duration_s: form.duration ? (t.duration_s && Math.round(t.duration_s / 60) === num(form.duration) ? t.duration_s : Math.round(num(form.duration) * 60)) : undefined,
        pace_low: fromClock(form.low), pace_high: fromClock(form.high),
        hr_zone: form.zone && item.sport === "run" ? Number(form.zone) : undefined,
      };
      const clean = Object.fromEntries(Object.entries(next).filter(([, v]) => v !== undefined));
      if (!sameTargets(clean, t)) {
        changes.targets = Object.keys(clean).length ? clean : null;
      }
    }
    if (!Object.keys(changes).length) return onCancel();
    apiFetch(`/api/agenda/${item.id}`, { method: "PATCH", body: JSON.stringify(changes) }).then(onSaved).catch((err) => setError(err.message));
  };
  const unit = item.sport === "run" ? "per km" : "per 100 m";
  return (
    <Card i={1}>
      <form onSubmit={save} className="stack">
        <label className="field">Title<input value={form.title} maxLength={80} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="field">Day<input type="date" value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} /></label>
        <label className="field">Note<textarea rows={2} maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
        {withTargets && (
          <div className="grid-form">
            <label className="field">Distance (km)<input inputMode="decimal" value={form.distance} onChange={(e) => setForm({ ...form, distance: e.target.value })} /></label>
            <label className="field">Duration (min)<input inputMode="numeric" value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} /></label>
            <label className="field">Pace from ({unit})<input placeholder="5:35" value={form.low} onChange={(e) => setForm({ ...form, low: e.target.value })} /></label>
            <label className="field">Pace to ({unit})<input placeholder="5:50" value={form.high} onChange={(e) => setForm({ ...form, high: e.target.value })} /></label>
            {item.sport === "run" && (
              <label className="field">Heart-rate zone
                <select value={form.zone} onChange={(e) => setForm({ ...form, zone: e.target.value })}>
                  <option value="">None</option>{[1, 2, 3, 4, 5].map((z) => <option key={z} value={z}>Zone {z}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
        <label className="row" style={{ gap: 8, fontSize: 14 }}>
          <input type="checkbox" checked={form.optional} onChange={(e) => setForm({ ...form, optional: e.target.checked })} /> Optional
        </label>
        {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <div className="row"><button className="btn primary" type="submit">Save</button><button className="btn" type="button" onClick={onCancel}>Cancel</button></div>
      </form>
    </Card>
  );
}

function PlanSection({ plan, item }: { plan: SessionPlan; item: AgendaItem }) {
  if (plan.kind === "zwift") {
    return (
      <div className="session-grid">
        <Card i={2}>
          <SectionHead title="The workout" />
          <PlanChart parts={plan.parts} />
          <div className="table-wrap">
            <table className="table" aria-label="Workout parts">
              <thead><tr><th>Part</th><th className="num">Time</th><th className="num">Power</th></tr></thead>
              <tbody>
                {plan.parts.map((p, n) => (
                  <tr key={n} className={p.work ? "work-row" : ""}>
                    <td>{p.label}</td>
                    <td className="num">{mmss(p.start_s)}–{mmss(p.end_s)}</td>
                    <td className="num">{p.from_w == null
                      ? `${Math.round(p.from_frac * 100)}${p.to_frac !== p.from_frac ? ` → ${Math.round(p.to_frac * 100)}` : ""}%`
                      : `${p.from_w}${p.to_w !== p.from_w ? ` → ${p.to_w}` : ""} W`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="stack">
          <div className="tiles">
            <Tile label="Duration" value={minutes(plan.duration_s)} i={0} />
            <Tile label="Sweet spot" value={`${plan.sweet_spot_min}′`} sub="at 84–97% FTP" i={1} />
            <Tile label="Est. TSS" value={String(plan.tss_est)} i={2} />
            <Tile label="FTP used" value={plan.ftp ? `${plan.ftp} W` : "–"} i={3} />
          </div>
          {!plan.ftp_is_set && <div className="note">Set your Zwift FTP on the <Link to="/body">Body page</Link> so these watts match Zwift.</div>}
          {item.note && <Card i={3}><SectionHead title="Note" /><p className="secondary" style={{ margin: 0 }}>{item.note}</p></Card>}
        </div>
      </div>
    );
  }
  if (plan.kind === "targets") {
    const sport = item.sport === "swim" ? "swim" : "run";
    return (
      <Card i={2}>
        <SectionHead title="The plan" />
        <div className="tiles">
          {plan.distance_m && <Tile label="Distance" value={plan.distance_m >= 1000 ? `${(plan.distance_m / 1000).toFixed(1)} km` : `${plan.distance_m} m`} i={0} />}
          {plan.duration_s && <Tile label="Duration" value={minutes(plan.duration_s)} i={1} />}
          {plan.pace_low && plan.pace_high && <Tile label="Pace" value={`${mmss(plan.pace_low)}–${paceText(plan.pace_high, sport)}`} i={2} />}
          {plan.hr_zone && <Tile label="Heart rate" value={`Zone ${plan.hr_zone}`} sub={plan.hr_bpm ? `${plan.hr_bpm[0]}–${plan.hr_bpm[1]} bpm` : undefined} i={3} />}
        </div>
        {item.note && <p className="secondary" style={{ marginBottom: 0 }}>{item.note}</p>}
        {!plan.distance_m && !plan.duration_s && !plan.pace_low && !item.note && <p className="muted" style={{ margin: 0 }}>No targets set. Use Edit to add some.</p>}
      </Card>
    );
  }
  if (plan.kind === "gym") {
    const upcoming = !item.done && item.day >= new Date().toISOString().slice(0, 10);
    return (
      <Card i={2}>
        <SectionHead title="The plan" right={plan.routine && upcoming ? <Link to={`/plan?day=${encodeURIComponent(plan.routine)}`} className="btn primary small" style={{ textDecoration: "none" }}>Plan it</Link> : undefined} />
        {plan.items.length ? (
          <ul className="list">
            {plan.items.map((p: PlanItem) => (
              <li key={p.id} className="session-plan-row">
                <span><strong>{p.exercise}</strong>{p.kind === "add" && <span className="muted"> · extra</span>}</span>
                <span className="secondary num">{doseLine(p)}{changeLabel(p) ? ` · ${changeLabel(p)}` : ""}</span>
              </li>
            ))}
          </ul>
        ) : <p className="muted" style={{ margin: 0 }}>Your routine shows here once it's in your Hevy history.</p>}
      </Card>
    );
  }
  return item.note ? <Card i={2}><p className="secondary" style={{ margin: 0 }}>{item.note}</p></Card> : null;
}

function ActualSection({ d }: { d: SessionDetail }) {
  const a = d.actual!;
  const { plan, item } = d;
  if (item.sport === "bike") {
    const work = (a.parts ?? []).filter((p) => p.avg_w != null);
    const avgWork = work.length ? Math.round(work.reduce((s, p) => s + (p.avg_w ?? 0), 0) / work.length) : null;
    const all = a.parts ?? [];
    const onTarget = all.filter((p) => p.status === "on_target").length;
    return (
      <>
        <div className="tiles">
          <Tile label="Time" value={minutes(a.moving_s ?? a.duration_s)} sub={plan.kind === "zwift" ? `planned ${minutes(plan.duration_s)}` : undefined} i={0} />
          <Tile label="Avg power" value={a.avg_power ? `${a.avg_power} W` : "–"} i={1} />
          {avgWork != null && <Tile label="Intervals" value={`${avgWork} W`} sub={all.some((p) => p.target_w) ? `${onTarget} of ${all.length} on target` : undefined} i={2} />}
          <Tile label="Avg HR" value={a.avg_hr ? `${a.avg_hr}` : "–"} i={3} />
          <Tile label="TSS" value={a.tss ? String(Math.round(a.tss)) : "–"} sub={plan.kind === "zwift" ? `planned ${plan.tss_est}` : undefined} i={4} />
        </div>
        {plan.kind === "zwift" && a.power && (
          <Card i={3}>
            <SectionHead title="Plan vs what you rode" right={<span className="legend"><span><i className="swatch" style={{ background: "var(--series-power)" }} />Your power</span><span><i className="swatch" style={{ background: "var(--accent)" }} />Target</span><span><i className="swatch" style={{ background: "var(--series-hr)" }} />Heart rate</span></span>} />
            <RideChart parts={plan.parts} a={a} ftp={plan.ftp} />
          </Card>
        )}
        {a.parts && a.parts.length > 0 && (
          <Card i={4}>
            <SectionHead title="Interval by interval" />
            <div className="table-wrap">
              <table className="table" aria-label="Interval by interval">
                <thead><tr><th>Part</th><th className="num">Target</th><th className="num">You</th><th className="num">HR</th><th className="num">Cadence</th><th /></tr></thead>
                <tbody>
                  {a.parts.map((p) => (
                    <tr key={p.label}><td>{p.label}</td><td className="num">{p.target_w ? `${p.target_w} W` : "–"}</td>
                      <td className="num">{p.avg_w != null ? `${p.avg_w} W` : "–"}</td><td className="num">{p.avg_hr ?? "–"}</td>
                      <td className="num">{p.avg_cadence ?? "–"}</td><td><StatusText status={p.status} /></td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>On target means within 3% of the target{plan.kind === "zwift" && plan.ftp ? `, using your FTP of ${plan.ftp} W` : ""}.</p>
          </Card>
        )}
      </>
    );
  }
  if (item.sport === "run" || item.sport === "swim") {
    const sport = item.sport;
    const t = plan.kind === "targets" ? plan : undefined;
    const pace = sport === "run" ? a.avg_pace_s_per_km : a.swim_pace_s_per_100m;
    const zoneTotal = a.zones ? Object.values(a.zones).reduce((s, v) => s + v, 0) : 0;
    return (
      <>
        <div className="tiles">
          <Tile label="Distance" value={a.distance_m ? (sport === "run" ? `${(a.distance_m / 1000).toFixed(2)} km` : `${Math.round(a.distance_m)} m`) : "–"}
            sub={t?.distance_m ? `planned ${sport === "run" ? `${(t.distance_m / 1000).toFixed(1)} km` : `${t.distance_m} m`}` : undefined} i={0} />
          <Tile label="Time" value={minutes(a.moving_s ?? a.duration_s)} sub={t?.duration_s ? `planned ${minutes(t.duration_s)}` : undefined} i={1} />
          <Tile label="Pace" value={paceText(pace, sport)} sub={t?.pace_low && t.pace_high ? `target ${mmss(t.pace_low)}–${mmss(t.pace_high)}` : undefined} i={2} />
          <Tile label="Avg HR" value={a.avg_hr ? `${a.avg_hr}` : "–"} sub={t && "hr_bpm" in t && t.hr_bpm ? `zone ${t.hr_zone}: ${t.hr_bpm[0]}–${t.hr_bpm[1]}` : undefined} i={3} />
          {sport === "swim" && a.swim_lengths && <Tile label="Lengths" value={String(a.swim_lengths)} i={4} />}
          {sport === "swim" && a.swim_strokes && <Tile label="Strokes" value={String(a.swim_strokes)} i={5} />}
        </div>
        {sport === "run" && a.pace && (
          <Card i={3}><SectionHead title="Pace" /><PaceChart a={a} low={t?.pace_low} high={t?.pace_high} /></Card>
        )}
        {a.splits && (
          <Card i={4}>
            <SectionHead title="Splits" />
            <div className="table-wrap">
              <table className="table" aria-label="Splits">
                <thead><tr><th>Km</th><th className="num">Pace</th><th className="num">HR</th><th /></tr></thead>
                <tbody>{a.splits.map((s) => (
                  <tr key={s.km}><td>{s.km}</td><td className="num">{paceText(s.pace, "run")}</td><td className="num">{s.avg_hr ?? "–"}</td>
                    <td>{s.status ? <StatusText status={s.status} /> : null}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        )}
        {a.zones && zoneTotal > 0 && (
          <Card i={5}>
            <SectionHead title="Time in heart-rate zones" />
            {Object.entries(a.zones).map(([z, s]) => (
              <div key={z} className="zone-row">
                <span>Zone {z}</span>
                <span className="zone-bar"><span className="grow-x" style={{ width: `${(s / zoneTotal) * 100}%` }} /></span>
                <span className="num secondary">{minutes(s)}</span>
              </div>
            ))}
          </Card>
        )}
      </>
    );
  }
  if (item.sport === "gym" && a.rows) {
    return (
      <Card i={2}>
        <SectionHead title="Plan vs what you did" />
        <div className="table-wrap">
          <table className="table" aria-label="Plan vs what you did">
            <thead><tr><th>Exercise</th><th>Planned</th><th>Did</th><th /></tr></thead>
            <tbody>
              {a.rows.map((r, n) => (
                <tr key={`${r.exercise}-${n}`} className={r.status === "skipped_by_you" ? "muted-row" : ""}>
                  <td><strong>{r.exercise}</strong>{r.extra && <span className="muted"> · extra</span>}{r.goal && <span className="goal-tag">{r.goal}</span>}</td>
                  <td className="num">{r.planned ? `${r.planned.sets} × ${r.planned.reps}${r.planned.weight_kg != null ? ` at ${r.planned.weight_kg} kg` : ""}` : "–"}</td>
                  <td className="num">{r.done.length ? r.done.map((s) => `${s.kg ?? "BW"}×${s.reps ?? 0}`).join(" · ") : "–"}</td>
                  <td><StatusText status={r.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    );
  }
  return null;
}

export default function Session() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [d, setD] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const load = () => apiFetch<SessionDetail>(`/api/agenda/${id}/detail`).then(setD).catch((e) => setError(e.message));
  useEffect(() => { setD(null); load(); }, [id]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <><Link to="/agenda" className="secondary" style={{ fontSize: 14, textDecoration: "none" }}>‹ Agenda</Link><p className="error">{error}</p></>;
  if (!d) return <p className="muted">Loading…</p>;
  const { item, plan, actual } = d;
  const remove = () => apiFetch(`/api/agenda/${item.id}`, { method: "DELETE" }).then(() => navigate(`/agenda?week=${item.day}`)).catch((e) => setError(e.message));

  return (
    <>
      <Link to={`/agenda?week=${item.day}`} className="secondary" style={{ fontSize: 14, textDecoration: "none" }}>‹ Agenda</Link>
      <Card i={0} variant={item.done ? "accent" : undefined} className="session-hero">
        <span className={`big-check${item.done ? " done pop" : ""}`} aria-hidden="true">{item.done ? "✓" : "to do"}</span>
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">{dayText(item.day)} · {SPORT_NAME[item.sport]} · {item.source === "coach" ? "planned with the coach" : "added by you"}</div>
          <h1 className="session-title">{item.title}</h1>
          {item.result && <div className="secondary">{item.result}</div>}
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            {item.goal && <span className="goal-tag">for your goal: {item.goal}</span>}
            {item.zwift_status && !item.done && <span className={`pill zwift ${item.zwift_status}`}>
              {item.zwift_status === "synced" ? `In Zwift ✓ as "${item.zwift?.filename.replace(/\.zwo$/, "")}"` : "Goes to Zwift at the next sync"}</span>}
            {item.optional && <span className="pill optional">Optional</span>}
          </div>
          {item.zwift_status === "pending" && !item.done && <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>Restart Zwift after the sync to see it under Custom Workouts.</div>}
        </div>
        <div className="row" style={{ gap: 8 }}>
          {actual && <Link className="btn" style={{ textDecoration: "none" }} to={`/activities/${actual.activity_id}`}>Full activity →</Link>}
          <button className="btn" onClick={() => setEditing((v) => !v)}>Edit</button>
          {!confirm ? <button className="btn danger" onClick={() => setConfirm(true)}>Delete</button>
            : <button className="btn danger" onClick={remove}>Yes, delete it</button>}
        </div>
      </Card>
      {editing && <Edit item={item} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />}
      {actual ? <ActualSection d={d} /> : <PlanSection plan={plan} item={item} />}
      {actual && plan.kind !== "note" && (
        <details className="card session-plan-details">
          <summary>What was planned</summary>
          <PlanSection plan={plan} item={item} />
        </details>
      )}
    </>
  );
}
