import type { AgendaItem, Targets } from "./agenda";
import type { PlanItem } from "./plan";

export interface Part { label: string; start_s: number; end_s: number; from_w: number | null; to_w: number | null; from_frac: number; to_frac: number; work: boolean }
export type Status = "on_target" | "above" | "below" | "faster" | "slower" | "done" | "close" | "skipped" | "skipped_by_you" | "added"
  | "no_target" | null;

export type SessionPlan =
  | { kind: "zwift"; ftp: number | null; ftp_is_set: boolean; parts: Part[]; duration_s: number; sweet_spot_min: number; tss_est: number }
  | ({ kind: "targets"; hr_bpm: [number, number] | null } & Targets)
  | { kind: "gym"; routine: string | null; items: PlanItem[] }
  | { kind: "note" };

export interface BlockRow {
  kind: "warmup" | "work" | "recovery" | "cooldown"; repeat: number | null;
  seconds: number | null; metres: number | null; pace_s_per_km: number | null; avg_hr: number | null;
  planned_goal: { time_s?: number; distance_m?: number } | null;
  planned_target: { pace_low?: number; pace_high?: number; hr_zone?: number } | null;
  in_target: boolean | null;
}

export interface SessionActual {
  activity_id: number; start_at: string; duration_s: number; moving_s: number | null; distance_m: number | null;
  avg_power: number | null; np: number | null; tss: number | null; avg_hr: number | null;
  avg_pace_s_per_km: number | null; swim_pace_s_per_100m: number | null; swim_lengths: number | null; swim_strokes: number | null;
  power?: [number, number][] | null; hr?: [number, number][] | null; pace?: [number, number][] | null;
  parts?: { label: string; target_w: number | null; avg_w: number | null; avg_hr: number | null; avg_cadence: number | null; status: Status }[];
  intervals_on_target?: boolean | null;
  splits?: { km: number; pace: number; avg_hr: number | null; status?: Status }[] | null;
  zones?: Record<string, number> | null;
  blocks?: { follows_plan: boolean; rows: BlockRow[] } | null;
  rows?: { exercise: string; planned: { sets: number; reps: string; weight_kg: number | null; dumbbell: "pair" | "each" | null } | null;
    done: { kg: number | null; reps: number | null }[]; status: Status; extra: boolean; goal: string | null }[];
}

export interface SessionDetail {
  item: AgendaItem; plan: SessionPlan; actual: SessionActual | null;
  /** Said for a run, ride or swim in the first two weeks after its time off: take it easy. */
  easy_back?: string | null;
}

const LABELS: Record<string, { text: string; tone: "good" | "near" | "muted" }> = {
  on_target: { text: "On target", tone: "good" },
  done: { text: "Done", tone: "good" },
  above: { text: "Above", tone: "near" },
  below: { text: "Below", tone: "near" },
  faster: { text: "Faster", tone: "near" },
  slower: { text: "Slower", tone: "near" },
  close: { text: "Close", tone: "near" },
  skipped: { text: "Skipped", tone: "muted" },
  skipped_by_you: { text: "Skipped by you", tone: "muted" },
  added: { text: "Added", tone: "muted" },
  no_target: { text: "–", tone: "muted" },  // ridden, but no FTP to compare with
};

/** Words for a comparison, never red: "below" and "close" are information, not failure. */
export function statusLabel(status: Status): { text: string; tone: "good" | "near" | "muted" } {
  return status ? LABELS[status] : { text: "Not ridden", tone: "muted" };
}
