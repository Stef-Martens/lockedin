import { describe, expect, it } from "vitest";
import { statusLabel } from "./session";

describe("session statuses", () => {
  it("names statuses without guilt", () => {
    expect(statusLabel("on_target")).toEqual({ text: "On target", tone: "good" });
    expect(statusLabel("below").text).toBe("Below");
    expect(statusLabel("skipped_by_you").text).toBe("Skipped by you");
    expect(statusLabel("close").text).toBe("Close");
    expect(statusLabel(null).text).toBe("Not ridden");
    expect(statusLabel("no_target").text).toBe("–");
  });
});
