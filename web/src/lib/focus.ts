import type { Sport } from "./format";

export type Effort = "easy" | "steady" | "hard" | "long";

export type FocusItem =
  | {
      type: "gym"; muscle_key: string; muscle_name: string; exercise: string; sets: number; reps: string;
      weight_kg: number | null; dumbbell: "pair" | "each" | null; estimate: boolean; reason: string; goal?: string | null;
    }
  | { type: "session"; sport: Sport; kind: Effort | "steady"; title: string; detail: string; reason: string; goal?: string | null };

export interface SportTotals { time_s: number; distance_m: number; sessions: number }
export type TotalsBySport = Record<Sport, SportTotals>;
export type WeekRow = { week_start: string } & Record<Sport, number>;

export interface Win { kind: string; title: string; detail: string; date: string; activity_id: number | null }

export interface Plateau { kind: string; title: string; detail: string; suggestion: string }

export interface Overview {
  totals: { week: TotalsBySport; month: TotalsBySport };
  weekly: WeekRow[];
  streak: number;
  comeback: { days_since: number | null; suggestion: string; title: string } | null;
  /** "Vacation until 27 Dec", or "no running until 17 Dec, no upper body until 2 Jan"; null when nothing is off today. */
  time_off_today: string | null;
  /** Shown for two weeks after an injury restriction ends. */
  back_from: { title: string; label: string | null } | null;
  wins: Win[];
  plateaus: Plateau[];
  focus: FocusItem[];
  measure_due: boolean;
  last_tape_measurement_on: string | null;
  checkin_due: boolean;
  next_checkin_on: string;
  last_checkin_on: string | null;
  hevy_due: boolean;
  hevy_last_upload_at: string | null;
}

export interface Coverage {
  key: string; name: string; region: string; sets_per_week: number; target_low: number; target_high: number;
  status: "low" | "ok" | "high";
}

/** A zone's [low, high] in W or bpm; the top power zone is open-ended ([lo, null]). */
export type ZoneBounds = [number, number | null];

/** `zones` in GET /api/focus, keyed by zone number ("1"–"5"). */
export interface FocusZones {
  max_hr: number | null;
  ftp: number | null;
  hr_zones: Record<string, ZoneBounds> | null;
  power_zones: Record<string, ZoneBounds> | null;
}

/** "151–176 W", or "≥ 252 W" for an open-ended top zone. */
export function zoneRange([lo, hi]: ZoneBounds, unit: string): string {
  return hi == null ? `≥ ${lo} ${unit}` : `${lo}–${hi} ${unit}`;
}

export interface EffortMix { sport: string; counts: Record<Effort, number>; unclassified: number }

/** One line for the "Focus this week" card. */
export function focusLine(item: FocusItem): { title: string; detail: string } {
  if (item.type === "session") return { title: item.title, detail: item.detail };
  let detail = `${item.sets} × ${item.reps}`;
  if (item.weight_kg != null) {
    // Same convention as the owner's Hevy logs: a pair total gets the per-hand weight spelled out too.
    const kg = item.weight_kg;
    detail += item.dumbbell === "pair" ? ` at ${kg} kg total (${kg / 2} kg each)`
      : item.dumbbell === "each" ? ` at ${kg} kg per dumbbell` : ` at ${kg} kg`;
  }
  if (item.estimate) detail += item.weight_kg != null ? " · estimate, start light" : ", start light";
  return { title: item.exercise, detail };
}

export function formatMinutes(m: number): string {
  const total = Math.round(m);
  if (total < 60) return `${total} min`;
  return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")}`;
}

/** "est. 1RM 96.0 kg (was 92.5)" → { value: "96.0 kg", note: "est. 1RM, was 92.5" } for the new-bests list. */
export function winParts(detail: string): { value: string; note: string } {
  const m = detail.match(/^(.*?)(?:^|\s)(\d+(?:[.:]\d+)?)(\s?(?:kg|W|km|\/km|\/100m))?(?=\s|$)(.*?)\s*\(was ([^)]+)\)$/);
  if (!m) return { value: "", note: detail };
  const [, pre, num, unit = "", post, was] = m;
  const label = [pre.trim(), post.trim()].filter(Boolean).join(" ");
  return { value: `${num}${unit}`, note: label ? `${label}, was ${was}` : `was ${was}` };
}
