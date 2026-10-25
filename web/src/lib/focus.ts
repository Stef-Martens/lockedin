import type { Sport } from "./format";

export type Effort = "easy" | "steady" | "hard" | "long";

export type FocusItem =
  | {
      type: "gym"; muscle_key: string; muscle_name: string; exercise: string; sets: number; reps: string;
      weight_kg: number | null; dumbbell: "pair" | "each" | null; estimate: boolean; reason: string;
    }
  | { type: "session"; sport: Sport; kind: Effort; title: string; detail: string; reason: string };

export interface SportTotals { time_s: number; distance_m: number; sessions: number }
export type TotalsBySport = Record<Sport, SportTotals>;
export type WeekRow = { week_start: string } & Record<Sport, number>;

export interface Win { kind: string; title: string; detail: string; date: string; activity_id: number | null }

export interface Overview {
  totals: { week: TotalsBySport; month: TotalsBySport };
  weekly: WeekRow[];
  streak: number;
  comeback: { days_since: number | null; suggestion: string } | null;
  wins: Win[];
  focus: FocusItem[];
  measure_due: boolean;
  last_tape_measurement_on: string | null;
}

export interface Coverage {
  key: string; name: string; region: string; sets_per_week: number; target_low: number; target_high: number;
  status: "low" | "ok" | "high";
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
