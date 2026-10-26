import { describe, expect, it } from "vitest";
import { weekDays, zwiftShape, type Block } from "./agenda";

describe("weekDays", () => {
  it("lists Monday to Sunday, across a clock change", () => {
    expect(weekDays("2026-10-19")).toEqual(["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25"]);
    expect(weekDays("2027-03-22")[6]).toBe("2027-03-28");
  });
});

describe("zwiftShape", () => {
  it("turns blocks into bars sized by time and power", () => {
    const blocks: Block[] = [
      { type: "warmup", duration_s: 600, from_power: 0.5, to_power: 0.75 },
      { type: "intervals", repeat: 2, on_s: 600, off_s: 300, on_power: 0.9, off_power: 0.55 },
      { type: "free", duration_s: 300 },
    ];
    const bars = zwiftShape(blocks);
    expect(bars).toHaveLength(6); // warm-up, on, off, on, off, free
    expect(bars.reduce((s, b) => s + b.width, 0)).toBeCloseTo(100);
    expect(bars[1].height).toBeCloseTo(100); // the hardest part fills the height
    expect(bars[2].height).toBeCloseTo((0.55 / 0.9) * 100);
    expect(bars[0].from).toBeCloseTo((0.5 / 0.9) * 100);
  });
});
