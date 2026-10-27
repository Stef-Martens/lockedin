import { describe, expect, it } from "vitest";
import { dayMs } from "../../lib/format";
import { timeOffAreas } from "./timeOffAreas";

describe("timeOffAreas", () => {
  it("shades the last day of a window too", () => {
    const [area] = timeOffAreas([{ start: "2026-10-05", end: "2026-10-05" }], "grey", dayMs, [dayMs("2026-10-01"), dayMs("2026-10-31")]);
    expect(area.props.x1).toBe(dayMs("2026-10-05"));
    expect(area.props.x2).toBe(dayMs("2026-10-06"));
  });
});
