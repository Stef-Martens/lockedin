import { describe, expect, it } from "vitest";
import { smooth } from "./smooth";

describe("smooth", () => {
  it("averages over a centred window, skipping gaps", () => {
    const pts = [10, 20, 30, null, 50].map((y, x) => ({ x, y }));
    expect(smooth(pts, 3).map((p) => p.y)).toEqual([15, 20, 25, null, 50]);
  });
  it("keeps x and leaves a window of 1 unchanged", () => {
    const pts = [{ x: 5, y: 1 }, { x: 6, y: 9 }];
    expect(smooth(pts, 1)).toEqual(pts);
  });
});
