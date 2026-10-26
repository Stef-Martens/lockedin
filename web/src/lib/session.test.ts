import { describe, expect, it } from "vitest";
import { mmss, paceText, statusLabel } from "./session";

describe("session formatters", () => {
  it("formats clock times and paces", () => {
    expect(mmss(0)).toBe("0:00");
    expect(mmss(600)).toBe("10:00");
    expect(mmss(3725)).toBe("1:02:05");
    expect(paceText(342, "run")).toBe("5:42/km");
    expect(paceText(126.7, "swim")).toBe("2:07/100 m");
    expect(paceText(null, "run")).toBe("–");
  });
  it("names statuses without guilt", () => {
    expect(statusLabel("on_target")).toEqual({ text: "On target", tone: "good" });
    expect(statusLabel("below").text).toBe("Below");
    expect(statusLabel("skipped_by_you").text).toBe("Skipped by you");
    expect(statusLabel("close").text).toBe("Close");
    expect(statusLabel(null).text).toBe("Not ridden");
  });
});
