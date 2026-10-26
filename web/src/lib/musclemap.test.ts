import { describe, expect, it } from "vitest";
import { muscleLabel, shadeLevel, shiftWeek, stripeOpacity } from "./musclemap";
import type { MapMuscle } from "./types";

const muscle = (over: Partial<MapMuscle>): MapMuscle => ({
  key: "quads", name: "Quads", region: "legs", target_low: 4, target_high: 14, sets: 0, days: [], history: [],
  last_trained: null, lift: null, cardio: [], suggestion: null, ...over,
});

describe("shadeLevel", () => {
  it("grades sets against the weekly target", () => {
    expect([0, 2, 4, 14, 15].map((s) => shadeLevel(s, 4, 14))).toEqual([0, 1, 2, 2, 3]);
  });
  it("treats any set as on target when the minimum is zero", () => {
    expect([shadeLevel(1, 0, 8), shadeLevel(9, 0, 8), shadeLevel(0, 0, 8)]).toEqual([2, 3, 0]);
  });
});

describe("stripeOpacity", () => {
  it("strengthens with minutes, full from two hours", () => {
    expect(stripeOpacity(0)).toBeCloseTo(0.35);
    expect(stripeOpacity(60)).toBeCloseTo(0.675);
    expect(stripeOpacity(240)).toBe(1);
  });
});

describe("muscleLabel", () => {
  it("names sets and cardio for screen readers", () => {
    expect(muscleLabel(muscle({ cardio: [{ sport: "bike", minutes: 46 }] }))).toBe("Quads: 0 sets this week, 46 minutes on the bike");
    expect(muscleLabel(muscle({ name: "Triceps", sets: 17 }))).toBe("Triceps: 17 sets this week");
    expect(muscleLabel(muscle({ name: "Lats", sets: 1.5, cardio: [{ sport: "swim", minutes: 40 }] })))
      .toBe("Lats: 1.5 sets this week, 40 minutes swimming");
  });
});

describe("shiftWeek", () => {
  it("moves by whole weeks, also across daylight saving changes", () => {
    expect(shiftWeek("2026-10-26", -1)).toBe("2026-10-19");
    expect(shiftWeek("2026-03-30", -1)).toBe("2026-03-23");
    expect(shiftWeek("2026-10-19", 1)).toBe("2026-10-26");
  });
});
