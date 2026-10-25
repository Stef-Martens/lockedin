import { describe, expect, it } from "vitest";
import { formatDate, formatDistance, formatDuration, formatPace, formatSwimPace } from "./format";

describe("format", () => {
  it("durations", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(605)).toBe("10:05");
    expect(formatDuration(59)).toBe("0:59");
  });
  it("paces", () => {
    expect(formatPace(300)).toBe("5:00 /km");
    expect(formatPace(337.5)).toBe("5:38 /km");
    expect(formatSwimPace(125)).toBe("2:05 /100m");
  });
  it("distances", () => {
    expect(formatDistance(12345, "bike")).toBe("12.3 km");
    expect(formatDistance(1500, "swim")).toBe("1500 m");
    expect(formatDistance(800, "run")).toBe("0.8 km");
  });
  it("dates in Brussels time", () => {
    // 22:30 UTC on Sun 25 Oct 2026 is 23:30 in Brussels
    expect(formatDate("2026-10-25T22:30:00Z")).toBe("Sun 25 Oct, 23:30");
  });
});
