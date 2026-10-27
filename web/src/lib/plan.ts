export type PlanKind = "routine" | "swap" | "add" | "missed";
/** "eased": a lift not done for 3+ weeks starts 10% lighter (20% after 8+ weeks). */
export type PlanChange = "up" | "same" | "welcome_back" | "eased" | "new" | null;

export interface PlanItem {
  id: string;
  exercise: string;
  equipment: string;
  kind: PlanKind;
  muscle: string | null;
  sets: number;
  reps: string;
  weight_kg: number | null;
  dumbbell: "pair" | "each" | null;
  change: PlanChange;
  estimate: boolean;
  last: { kg: number | null; reps: number | null }[];
  replaces: string | null;
  reason: string | null;
  goal: string | null;
  skipped: boolean;
  suggested: boolean;
  /** Lighter sets before the top weight last time (ramping up); the target covers only the top-weight sets. */
  lighter_sets?: number;
  goal_extra?: boolean;  // one of its sets is the goal's extra; the session counts as done without it
}

export interface Plan { id: number; day: string | null; built_on: string; comeback: boolean; items: PlanItem[] }
export interface PlanDays {
  days: { title: string; last_done: string; exercise_count: number }[];
  missed_available: boolean;
  comeback: boolean;
  goals: { id: number; text: string; target: string | null }[];
}
export interface Preferences { avoid_muscles: string[]; never_exercises: string[]; coach_notes: string }

const kg = (x: number) => `${Number.isInteger(x) ? x : x.toFixed(1)}`;

/** What changed since last time, in a few words; null when there's nothing to say. */
export function changeLabel(item: PlanItem): string | null {
  switch (item.change) {
    case "up": {
      if (item.weight_kg == null) return "One more rep";
      const before = Math.max(...item.last.map((s) => s.kg ?? 0));
      const diff = item.weight_kg - before;
      return item.dumbbell === "pair" ? `Up ${kg(diff)} kg (${kg(diff / 2)} kg each)` : `Up ${kg(diff)} kg`;
    }
    case "same": return "Same weight, aim for one more rep";
    case "welcome_back": {
      // In a comeback a lift you skipped for a while is eased too, but keeps this label: say which it is.
      const before = Math.max(0, ...item.last.map((s) => s.kg ?? 0));
      return item.weight_kg != null && before > 0 && item.weight_kg < before
        ? "Welcome back: lighter than last time" : "Welcome back: same as last time";
    }
    case "eased": return "Back after a break: lighter";
    case "new": return "New · start light";
    default: return null;
  }
}

/** "3 × 8–12 at 64 kg total (32 kg each)", in the owner's Hevy convention. */
export function doseLine(item: PlanItem): string {
  const dose = `${item.sets} × ${item.reps}`;
  if (item.weight_kg == null) return dose;
  const w = item.weight_kg;
  if (item.dumbbell === "pair") return `${dose} at ${kg(w)} kg total (${kg(w / 2)} kg each)`;
  if (item.dumbbell === "each") return `${dose} at ${kg(w)} kg per dumbbell`;
  return `${dose} at ${kg(w)} kg`;
}

export function lastLine(item: PlanItem): string | null {
  if (!item.last.length) return null;
  return "last: " + item.last.map((s) => `${s.kg == null ? "BW" : kg(s.kg)}×${s.reps ?? 0}`).join(" · ");
}
