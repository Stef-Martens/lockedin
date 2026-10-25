import { describe, expect, it } from "vitest";
import { focusLine, formatMinutes, type FocusItem } from "./focus";

const gym = (over: Partial<Extract<FocusItem, { type: "gym" }>>): FocusItem => ({
  type: "gym", muscle_key: "triceps", muscle_name: "Triceps", exercise: "Triceps Extension (Cable)", sets: 3, reps: "8–12",
  weight_kg: 27.5, dumbbell: null, estimate: false, reason: "Triceps: 0 sets/week, aim for 8–14", ...over,
});

describe("focusLine", () => {
  it("own exercise with weight", () => {
    expect(focusLine(gym({}))).toEqual({ title: "Triceps Extension (Cable)", detail: "3 × 8–12 at 27.5 kg" });
  });
  it("estimated weight for a pair of dumbbells (logged as total)", () => {
    expect(focusLine(gym({ exercise: "Shrug (Dumbbell)", weight_kg: 40, dumbbell: "pair", estimate: true })).detail)
      .toBe("3 × 8–12 at 40 kg total (20 kg each) · estimate, start light");
  });
  it("pair totals are whole kilos per hand", () => {
    expect(focusLine(gym({ weight_kg: 44, dumbbell: "pair" })).detail).toBe("3 × 8–12 at 44 kg total (22 kg each)");
  });
  it("weight logged per dumbbell", () => {
    expect(focusLine(gym({ weight_kg: 20, dumbbell: "each" })).detail).toBe("3 × 8–12 at 20 kg per dumbbell");
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

import { winParts } from "./focus";

describe("winParts", () => {
  it("splits each kind of win detail into a big value and a note", () => {
    expect(winParts("est. 1RM 96.0 kg (was 92.5)")).toEqual({ value: "96.0 kg", note: "est. 1RM, was 92.5" });
    expect(winParts("248 W (was 241)")).toEqual({ value: "248 W", note: "was 241" });
    expect(winParts("45.0 km ride (was 30.0)")).toEqual({ value: "45.0 km", note: "ride, was 30.0" });
    expect(winParts("5:10 /km (was 5:30)")).toEqual({ value: "5:10 /km", note: "was 5:30" });
    expect(winParts("2:05 /100m (was 2:10)")).toEqual({ value: "2:05 /100m", note: "was 2:10" });
    expect(winParts("12 sessions in the last 4 weeks (was 6)")).toEqual({ value: "12", note: "sessions in the last 4 weeks, was 6" });
  });
  it("falls back to the whole text", () => {
    expect(winParts("something else")).toEqual({ value: "", note: "something else" });
  });
});
