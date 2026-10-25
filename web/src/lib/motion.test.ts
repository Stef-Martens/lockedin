import { describe, expect, it } from "vitest";
import { easeOutCubic, stagger } from "./motion";

describe("motion", () => {
  it("staggers animation delays", () => {
    expect(stagger(0)).toEqual({ animationDelay: "0.05s" });
    expect(stagger(2)).toEqual({ animationDelay: "0.13s" });
    expect(stagger(1, 0.3, 0.1)).toEqual({ animationDelay: "0.40s" });
  });
  it("eases out", () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(1)).toBe(1);
    expect(easeOutCubic(0.5)).toBeCloseTo(0.875);
  });
});
