import { formatDuration, shortDay } from "./format";
import { formNumber, formWords, loadNumber } from "./load";
import type { TimeOffWindow } from "./timeoff";

/** GET /api/forecast: where each goal, fitness, race times and FTP are heading. */
export type Point = [string, number];                       // [day "YYYY-MM-DD", value]
export type Band = [string, number, number, number];         // [day, likely, low, high]

export interface GoalForecast {
  goal_id: number; text: string;
  kind: "lift" | "ftp" | "distance" | "time" | "body";
  unit: "kg" | "W" | "km" | "min" | "cm";
  lower_is_better: boolean;
  target: number; current: number | null;
  deadline: string | null;
  history: Point[];            // weekly, oldest first
  projection: Band[];          // weekly from the last history point; [] when there's no trend
  eta: { likely: string; early: string | null; late: string | null } | null;
  status: "reached" | "on_track" | "behind" | "eta" | "not_at_this_pace" | "too_little_data";
  summary: string;             // ready-to-show plain English, e.g. "Around mid-March (likely Feb–May)"
}

export interface RacePrediction {
  name: string; km: number; seconds: number;
  from: { activity_id: number; day: string; km: number; seconds: number };
}

export interface ForecastDay { day: string; fitness: number; fatigue: number; form: number; planned: boolean }

export interface Forecast {
  goals: GoalForecast[];
  race: { predictions: RacePrediction[]; history: Point[]; note: string } | null;   // history = predicted 5k seconds
  fitness: { days: ForecastDay[] } | null;
  ftp: { now: number; source: "zwift" | "owner" | "estimate"; history: Point[]; projection: Band[]; summary: string } | null;
  /** Time off since the charts' first week, to shade. */
  time_off: TimeOffWindow[];
}

export type Unit = GoalForecast["unit"];

/** At most one decimal, none when it's whole: 102.5, 100. */
const tidy = (v: number) => String(Number(v.toFixed(1)));

/** A goal value as a bare number for axis ticks; minutes as m:ss or h:mm:ss. */
export function goalTick(v: number, unit: Unit): string {
  if (unit === "min") return formatDuration(v * 60);
  return unit === "W" ? String(Math.round(v)) : tidy(v);
}

/** A goal value with its unit: "102.5 kg", "250 W", "24:30" (minutes need no unit once they're m:ss). */
export function goalValue(v: number, unit: Unit): string {
  return unit === "min" ? goalTick(v, unit) : `${goalTick(v, unit)} ${unit}`;
}

/** The status chip: its words and the .pill variant that colours it. */
export const STATUS: Record<GoalForecast["status"], { label: string; pill: string }> = {
  reached: { label: "Reached", pill: "done" },
  on_track: { label: "On track", pill: "goal" },
  behind: { label: "Behind", pill: "behind" },
  eta: { label: "No date yet", pill: "" },
  not_at_this_pace: { label: "Not at this pace", pill: "behind" },
  too_little_data: { label: "Too little data", pill: "optional" },
};

/** Who set the FTP, the way the Bike trends card says it. */
export const FTP_FROM: Record<NonNullable<Forecast["ftp"]>["source"], string> = { zwift: "from Zwift", owner: "yours", estimate: "estimated" };

/**
 * The fitness forecast in one sentence: fitness on the first planned day against the last day, and form on the
 * last day, in the Training load card's words. Null when nothing is planned.
 */
export function aheadLine(days: ForecastDay[]): string | null {
  const ahead = days.filter((d) => d.planned);
  if (!ahead.length) return null;
  const first = ahead[0];
  const last = ahead[ahead.length - 1];
  const weeks = Math.round(ahead.length / 7);
  const span = weeks <= 1 ? "week" : `${["two", "three", "four"][weeks - 2] ?? weeks} weeks`;
  return `Do your planned ${span} and fitness goes ${loadNumber(first.fitness)} → ${loadNumber(last.fitness)}; `
    + `form on ${shortDay(last.day)}: ${formNumber(last.form)} (${formWords(last.form).toLowerCase()})`;
}
