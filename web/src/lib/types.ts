import type { FocusItem } from "./focus";
import type { Sport } from "./format";

export interface ActivitySummary {
  id: number;
  source: "zwift" | "healthfit" | "hevy";
  sport: Sport;
  sub_type: string | null;
  start_at: string;
  end_at: string;
  duration_s: number;
  moving_s: number | null;
  distance_m: number | null;
  elevation_m: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_power: number | null;
  max_power: number | null;
  avg_cadence: number | null;
  np: number | null;
  if_: number | null;
  tss: number | null;
  avg_pace_s_per_km: number | null;
  swim_pace_s_per_100m: number | null;
  calories: number | null;
  superseded_by: number | null;
  hr_merged_from: number | null;
  title: string | null;
  set_count: number | null;
}

export interface Streams {
  t_offset: number[];
  power: (number | null)[] | null;
  hr: (number | null)[] | null;
  cadence: (number | null)[] | null;
  speed: (number | null)[] | null;
  altitude: (number | null)[] | null;
  distance: (number | null)[] | null;
}

export interface GymSet {
  exercise: string;
  exercise_order: number;
  set_index: number;
  set_type: string;
  weight_kg: number | null;
  reps: number | null;
  rpe: number | null;
  e1rm: number | null;
  notes: string | null;
  duration_s: number | null;
  distance_km: number | null;
}

export interface ActivityDetail extends ActivitySummary {
  pool_length_m: number | null;
  swim_lengths: number | null;
  swim_strokes: number | null;
  best_20m_power: number | null;
  streams: Streams | null;
  sets: GymSet[] | null;
  superseded_by_summary: ActivitySummary | null;
  hr_merged_from_summary: ActivitySummary | null;
  duplicates: ActivitySummary[];
}

export interface ActivityPage {
  items: ActivitySummary[];
  next_before: string | null;
}

export interface SourceStatus {
  last_import_at: string | null;
  count: number;
}

export interface Status {
  zwift: SourceStatus;
  healthfit: SourceStatus;
  hevy: SourceStatus;
  last_tape_measurement_on: string | null;
}

export interface FitResult {
  status: "imported" | "duplicate" | "empty" | "error";
  sha256: string;
  activity_id: number | null;
  error: string | null;
}

export interface HevyResult {
  new: number;
  updated: number;
  unchanged: number;
  skipped: [number, string][];
}

export interface Profile {
  date_of_birth: string | null;
  height_cm: number | null;
  sex: "male" | "female" | null;
  max_hr_override: number | null;
  ftp_override: number | null;
  resting_hr_override: number | null;
  dumbbell_weights: "pair" | "each";
  reminder_weeks: 1 | 2 | 4;
  reminder_hevy: boolean;
}

export interface MeasurementType {
  id: number;
  name: string;
  unit: string;
  kind: "weight" | "tape" | "other";
}

export interface Measurement {
  id: number;
  type_id: number;
  measured_on: string;
  value: number;
  note: string | null;
}

export type CardioSport = "bike" | "run" | "swim";
/** A focus-engine gym suggestion; render it with focusLine({ type: "gym", ...s }). */
export type GymSuggestion = Omit<Extract<FocusItem, { type: "gym" }>, "type">;

export interface MapMuscle {
  key: string;
  name: string;
  region: string;
  target_low: number;
  target_high: number;
  sets: number;
  days: { date: string; exercises: { name: string; sets: number }[] }[];
  history: { week_start: string; sets: number }[];
  last_trained: string | null;
  lift: { exercise: string; first_e1rm: number; latest_e1rm: number; status: "trend" | "new" | "not_lately" } | null;
  cardio: { sport: CardioSport; minutes: number }[];
  suggestion: GymSuggestion | null;
  /** Left out in the owner's preferences (e.g. an injured lower back). */
  left_out?: boolean;
  /** Active goals whose lift trains this muscle. */
  goals?: string[];
}

export interface MuscleMap {
  week_start: string;
  is_current: boolean;
  first_week: string | null;
  trained_count: number;
  /** Muscles that count: 20 minus the ones left out. */
  total?: number;
  cardio: { sport: CardioSport; minutes: number; days: string[] }[];
  muscles: MapMuscle[];
}
