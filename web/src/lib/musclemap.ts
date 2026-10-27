import { dayMonth } from "./format";
import type { CardioSport, MapMuscle } from "./types";

export type Shade = 0 | 1 | 2 | 3;

/** Grey, a little, on target, lots — against the muscle's weekly set target. */
export function shadeLevel(sets: number, low: number, high: number): Shade {
  if (sets <= 0) return 0;
  if (sets > high) return 3;
  return sets < low ? 1 : 2;
}

/** Cardio stripes strengthen with the week's minutes, full from two hours. */
export function stripeOpacity(minutes: number): number {
  return 0.35 + (0.65 * Math.min(Math.max(minutes, 0), 120)) / 120;
}

export const CARDIO_COLOR: Record<CardioSport, string> = {
  bike: "var(--sport-bike)", run: "var(--sport-run)", swim: "var(--sport-swim)",
};
export const CARDIO_PHRASE: Record<CardioSport, string> = {
  bike: "on the bike", run: "running", swim: "swimming",
};

const num = (x: number) => (Number.isInteger(x) ? `${x}` : x.toFixed(1));

export function muscleLabel(m: MapMuscle): string {
  if (m.left_out) return `${m.name}: left out in your preferences`;
  if (m.off_until) return `${m.name}: off until ${dayMonth(m.off_until)}`;
  const cardio = m.cardio.map((c) => `, ${c.minutes} minutes ${CARDIO_PHRASE[c.sport]}`).join("");
  return `${m.name}: ${num(m.sets)} sets this week${cardio}`;
}

/** ISO Monday moved by whole weeks; works on calendar dates so DST can't shift it. */
export function shiftWeek(weekStart: string, by: number): string {
  const [y, mo, d] = weekStart.split("-").map(Number);
  const t = new Date(Date.UTC(y, mo - 1, d + 7 * by));
  return t.toISOString().slice(0, 10);
}
