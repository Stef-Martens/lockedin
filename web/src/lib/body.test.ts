import { describe, expect, it } from "vitest";
import { historyRows, parseValue, TIPS } from "./body";

describe("historyRows", () => {
  it("lists check-ins newest first with change vs the previous check-in", () => {
    const rows = historyRows([
      { measured_on: "2026-10-26", values: { "1": 78.1, "2": 101 } },
      { measured_on: "2026-10-12", values: { "1": 79, "3": 36 } },
    ], [1, 2, 3]);
    expect(rows.map((r) => r.measured_on)).toEqual(["2026-10-26", "2026-10-12"]);
    expect(rows[0].cells).toEqual([
      { value: 78.1, delta: -0.9 },
      { value: 101, delta: null },
      { value: null, delta: null },
    ]);
    expect(rows[1].cells[0]).toEqual({ value: 79, delta: null });
  });
});

describe("parseValue", () => {
  it("accepts comma decimals and rejects blanks or zero", () => {
    expect(parseValue("36,5")).toBe(36.5);
    expect(parseValue(" 78.4 ")).toBe(78.4);
    expect(parseValue("")).toBeNull();
    expect(parseValue("0")).toBeNull();
    expect(parseValue("abc")).toBeNull();
  });
});

describe("TIPS", () => {
  it("has a tip for every default measurement", () => {
    for (const n of ["Weight", "Chest", "Left arm", "Right arm", "Waist", "Hips", "Left thigh", "Right thigh", "Shoulders"]) {
      expect(TIPS[n]).toBeTruthy();
    }
  });
});
