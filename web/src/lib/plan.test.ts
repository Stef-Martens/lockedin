import { describe, expect, it } from "vitest";
import { changeLabel, doseLine, lastLine } from "./plan";
import type { PlanItem } from "./plan";

const item = (over: Partial<PlanItem>): PlanItem => ({
  id: "a", exercise: "Bench Press (Barbell)", equipment: "barbell", kind: "routine", muscle: "mid_lower_chest",
  sets: 3, reps: "8–12", weight_kg: 82.5, dumbbell: null, change: "up", estimate: false, last: [], replaces: null,
  reason: null, goal: null, skipped: false, suggested: false, ...over,
});

describe("changeLabel", () => {
  it("names each kind of change", () => {
    expect(changeLabel(item({ change: "up", last: [{ kg: 80, reps: 12 }] }))).toBe("Up 2.5 kg");
    expect(changeLabel(item({ change: "up", weight_kg: null, reps: "13", last: [{ kg: null, reps: 12 }] }))).toBe("One more rep");
    expect(changeLabel(item({ change: "same" }))).toBe("Same weight, aim for one more rep");
    expect(changeLabel(item({ change: "welcome_back" }))).toBe("Welcome back: same as last time");
    expect(changeLabel(item({ change: "new" }))).toBe("New · start light");
    expect(changeLabel(item({ change: null }))).toBeNull();
  });
});

describe("doseLine", () => {
  it("follows the owner's dumbbell convention", () => {
    expect(doseLine(item({}))).toBe("3 × 8–12 at 82.5 kg");
    expect(doseLine(item({ weight_kg: 64, dumbbell: "pair" }))).toBe("3 × 8–12 at 64 kg total (32 kg each)");
    expect(doseLine(item({ weight_kg: 14, dumbbell: "each" }))).toBe("3 × 8–12 at 14 kg per dumbbell");
    expect(doseLine(item({ weight_kg: null, reps: "13" }))).toBe("3 × 13");
  });
});

describe("lastLine", () => {
  it("summarises last time's sets", () => {
    expect(lastLine(item({ last: [{ kg: 80, reps: 8 }, { kg: 77.5, reps: 7 }, { kg: null, reps: 10 }] }))).toBe("last: 80×8 · 77.5×7 · BW×10");
    expect(lastLine(item({ last: [] }))).toBeNull();
  });
});
