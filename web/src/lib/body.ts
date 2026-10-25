export interface Checkin {
  measured_on: string;
  values: Record<string, number>;
}

/** Where to put the tape, so every check-in is measured the same way. */
export const TIPS: Record<string, string> = {
  Weight: "Morning, before eating",
  Chest: "At nipple height, arms down, breathe out",
  Shoulders: "Widest point around both shoulders",
  "Left arm": "Widest point of the biceps, relaxed",
  "Right arm": "Widest point of the biceps, relaxed",
  Waist: "At the navel, relaxed, after breathing out",
  Hips: "Widest point around the glutes",
  "Left thigh": "Widest point, just below the glutes",
  "Right thigh": "Widest point, just below the glutes",
};

/** Typed value → number, accepting a comma decimal; blank, zero or junk → null (skipped on save). */
export function parseValue(raw: string): number | null {
  const v = parseFloat(raw.trim().replace(",", "."));
  return Number.isFinite(v) && v > 0 ? v : null;
}

/** History newest first; each cell's delta is against the previous (older) check-in that has that type. */
export function historyRows(checkins: Checkin[], typeIds: number[]) {
  const sorted = [...checkins].sort((a, b) => b.measured_on.localeCompare(a.measured_on));
  return sorted.map((c, i) => ({
    measured_on: c.measured_on,
    cells: typeIds.map((id) => {
      const value = c.values[String(id)] ?? null;
      const prev = sorted.slice(i + 1).find((o) => o.values[String(id)] != null)?.values[String(id)] ?? null;
      return { value, delta: value != null && prev != null ? Math.round((value - prev) * 10) / 10 : null };
    }),
  }));
}
