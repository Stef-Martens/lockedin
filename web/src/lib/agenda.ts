export type AgendaSport = "gym" | "bike" | "run" | "swim" | "rest" | "other";
export type Block =
  | { type: "warmup" | "cooldown"; duration_s: number; from_power: number; to_power: number }
  | { type: "steady"; duration_s: number; power: number }
  | { type: "intervals"; repeat: number; on_s: number; off_s: number; on_power: number; off_power: number }
  | { type: "free"; duration_s: number };

export interface AgendaItem {
  id: number;
  day: string;
  sport: AgendaSport;
  title: string;
  note: string | null;
  optional: boolean;
  routine: string | null;
  zwift: { blocks: Block[]; duration_s: number; summary: string; filename: string } | null;
  zwift_status: "synced" | "pending" | null;
  sort: number;
  source: "coach" | "manual";
  done: boolean;
  activity_id: number | null;
  targets: Targets | null;
  goal_id: number | null;
  goal: string | null;
  /** "Done · 66′ · 128 W" once ticked off. */
  result: string | null;
}
export interface Targets { distance_m?: number; duration_s?: number; pace_low?: number; pace_high?: number; hr_zone?: number }
export interface AgendaWeek { week_start: string; today: string; items: AgendaItem[] }

export const SPORT_COLOR: Record<AgendaSport, string> = {
  gym: "var(--sport-gym)", bike: "var(--sport-bike)", run: "var(--sport-run)", swim: "var(--sport-swim)",
  rest: "var(--ink-muted)", other: "var(--sport-other)",
};
export const SPORT_NAME: Record<AgendaSport, string> = {
  gym: "Gym", bike: "Zwift / bike", run: "Run", swim: "Swim", rest: "Rest", other: "Other",
};

/** The seven ISO dates of the week starting on `weekStart` (calendar maths, so DST can't shift a day). */
export function weekDays(weekStart: string): string[] {
  const [y, m, d] = weekStart.split("-").map(Number);
  return Array.from({ length: 7 }, (_, i) => new Date(Date.UTC(y, m - 1, d + i)).toISOString().slice(0, 10));
}

export interface Bar { width: number; height: number; from: number; easy: boolean }

/** Bars for a small workout chart: width = share of the time, height = power relative to the hardest moment. */
export function zwiftShape(blocks: Block[]): Bar[] {
  const parts: { s: number; from: number; to: number; easy: boolean }[] = [];
  for (const b of blocks) {
    if (b.type === "intervals") {
      for (let i = 0; i < b.repeat; i++) {
        parts.push({ s: b.on_s, from: b.on_power, to: b.on_power, easy: false });
        parts.push({ s: b.off_s, from: b.off_power, to: b.off_power, easy: true });
      }
    } else if (b.type === "steady") parts.push({ s: b.duration_s, from: b.power, to: b.power, easy: false });
    else if (b.type === "free") parts.push({ s: b.duration_s, from: 0.5, to: 0.5, easy: true });
    else parts.push({ s: b.duration_s, from: b.from_power, to: b.to_power, easy: true });
  }
  const total = parts.reduce((n, p) => n + p.s, 0) || 1;
  const peak = Math.max(...parts.map((p) => Math.max(p.from, p.to)), 0.01);
  return parts.map((p) => ({ width: (p.s / total) * 100, height: (p.to / peak) * 100, from: (p.from / peak) * 100, easy: p.easy }));
}
