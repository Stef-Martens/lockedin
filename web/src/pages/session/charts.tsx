import { useState, type PointerEvent, type ReactNode } from "react";
import { formatDuration, formatPace } from "../../lib/format";
import type { Part, SessionActual } from "../../lib/session";

type Tick = { at: number; text: string };

/** Minute marks every 5, 10, 20, 30 or 60 minutes: whichever keeps it to about seven. */
function timeTicks(end: number): Tick[] {
  const step = [300, 600, 1200, 1800, 3600].find((s) => end / s <= 7) ?? 7200;
  return Array.from({ length: Math.floor(end / step) + 1 }, (_, m) => ({ at: (m * step) / end, text: `${(m * step) / 60}′` }))
    .filter((t) => t.at <= 0.96);
}

/**
 * Pointer position over the chart as seconds into the session. A mouse shows it while hovering; a finger
 * shows it on a tap and scrubs sideways (the chart has touch-action: pan-y, so up and down still scrolls),
 * and the readout stays after the finger lifts.
 */
export function useHoverTime(end: number) {
  const [t, setT] = useState<number | null>(null);
  const at = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    if (box.width > 0) setT(Math.max(0, Math.min(end, ((e.clientX - box.left) / box.width) * end)));
  };
  const handlers = {
    onPointerDown: at,
    onPointerMove: at,
    onPointerLeave: (e: PointerEvent<SVGSVGElement>) => { if (e.pointerType === "mouse") setT(null); },
  };
  return [t, handlers] as const;
}

const nearest = (pts: [number, number][], t: number) =>
  pts.reduce<[number, number] | null>((best, p) => (!best || Math.abs(p[0] - t) < Math.abs(best[0] - t) ? p : best), null);

/** A chart whose value and time labels are HTML, so they stay readable however narrow the chart gets.
 * `ticks` are in the SVG's own units (0 at the top, `height` at the bottom). */
function ChartFrame({ label, height, ticks, times, readout, children }: {
  label: string; height: number; ticks: Tick[]; times: Tick[]; readout?: string | null; children: ReactNode;
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

const chartHeight = (px: number) => ({ ["--chart-h" as string]: `${px}px` });

/** The planned blocks: bars sized by time and power, with the FTP as a dashed line. */
export function PlanChart({ parts }: { parts: Part[] }) {
  const end = parts[parts.length - 1]?.end_s || 1;
  const top = Math.max(1.1, ...parts.map((p) => Math.max(p.from_frac, p.to_frac))) * 1.05;
  const y = (f: number) => 165 - (f / top) * 160;
  return (
    <ChartFrame label="Workout shape" height={165} ticks={[{ at: y(1), text: "FTP" }, { at: y(0.5), text: "50%" }]} times={timeTicks(end)}>
      <svg className="session-chart" style={chartHeight(150)} viewBox="0 0 640 165" preserveAspectRatio="none" role="img" aria-label="Workout shape">
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
export function RideChart({ parts, a, ftp }: { parts: Part[]; a: SessionActual; ftp: number | null }) {
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
    readout = `${formatDuration(hover)}${w ? ` · ${Math.round(w[1])} W` : ""}${tw != null ? ` · target ${tw} W` : ""}`;
  }
  return (
    <ChartFrame label="Power over the ride" height={200} ticks={ticks} times={timeTicks(end)} readout={readout}>
      <svg className="session-chart scrub" style={chartHeight(200)} viewBox="0 0 1000 200" preserveAspectRatio="none"
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
export function PaceChart({ a, low, high }: { a: SessionActual; low?: number; high?: number }) {
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
    <ChartFrame label="Pace over the run" height={190} ticks={marks.map((v) => ({ at: y(v), text: formatDuration(v) }))} times={timeTicks(end)}
      readout={hover != null && p ? `${formatDuration(hover)} · ${formatPace(p[1])}` : null}>
      <svg className="session-chart scrub" style={chartHeight(180)} viewBox="0 0 1000 190" preserveAspectRatio="none"
        role="img" aria-label="Pace over the run" {...handlers}>
        {low && high && <rect x="0" width="1000" y={y(low)} height={Math.max(2, y(high) - y(low))} className="pace-band" />}
        <polyline points={pace.map(([t, v]) => `${((t / end) * 1000).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} className="pace-line" />
        {hover != null && <line x1={(hover / end) * 1000} x2={(hover / end) * 1000} y1="0" y2="190" className="cursor" />}
      </svg>
    </ChartFrame>
  );
}
