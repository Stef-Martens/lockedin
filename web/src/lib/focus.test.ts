import { describe, expect, it } from "vitest";
import { focusLine, formatMinutes, type FocusItem } from "./focus";

const gym = (over: Partial<Extract<FocusItem, { type: "gym" }>>): FocusItem => ({
  type: "gym", muscle_key: "triceps", muscle_name: "Triceps", exercise: "Triceps Extension (Cable)", sets: 3, reps: "8–12",
  weight_kg: 27.5, per_dumbbell: false, estimate: false, reason: "Triceps: 0 sets/week, aim for 8–14", ...over,
});

describe("focusLine", () => {
  it("own exercise with weight", () => {
    expect(focusLine(gym({}))).toEqual({ title: "Triceps Extension (Cable)", detail: "3 × 8–12 at 27.5 kg" });
  });
  it("estimated per-dumbbell weight", () => {
    expect(focusLine(gym({ exercise: "Shrug (Dumbbell)", weight_kg: 55, per_dumbbell: true, estimate: true })).detail)
      .toBe("3 × 8–12 at 55 kg per dumbbell · estimate, start light");
  });
  it("new exercise without a basis for a weight", () => {
    expect(focusLine(gym({ weight_kg: null, estimate: true })).detail).toBe("3 × 8–12, start light");
  });
  it("bodyweight", () => {
    expect(focusLine(gym({ exercise: "Pull Up", weight_kg: null, reps: "8–10" })).detail).toBe("3 × 8–10");
  });
  it("run or ride session", () => {
    expect(focusLine({ type: "session", sport: "run", kind: "long", title: "Long easy run",
      detail: "60–75 min in zone 2 (HR 114–133 bpm)", reason: "No long run in the last 3 weeks" }))
      .toEqual({ title: "Long easy run", detail: "60–75 min in zone 2 (HR 114–133 bpm)" });
  });
});

describe("formatMinutes", () => {
  it("formats", () => {
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(65)).toBe("1 h 05");
    expect(formatMinutes(0)).toBe("0 min");
  });
});
