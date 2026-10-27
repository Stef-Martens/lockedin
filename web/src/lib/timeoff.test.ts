import { describe, expect, it } from "vitest";
import { bandText, entryLine, formBody, formFromEntry, type TimeOffEntry } from "./timeoff";

const OPERATION: TimeOffEntry = {
  id: 1, reason: "injury", label: "Operation", start: "2026-12-03", end: "2027-01-02",
  restrictions: [{ category: "run", until: "2026-12-17" }, { category: "upper", until: "2027-01-02" }],
};

describe("time off", () => {
  it("writes an entry on one line", () => {
    expect(entryLine(OPERATION)).toBe("Operation · from 3 Dec · no running until 17 Dec, no upper body until 2 Jan");
    expect(entryLine({ ...OPERATION, label: null, reason: "vacation", restrictions: [{ category: "all", until: "2026-12-27" }] }))
      .toBe("Vacation · from 3 Dec · everything off until 27 Dec");
  });

  it("names the band on a day", () => {
    expect(bandText({ day: "2026-12-04", reason: "injury", label: "Operation", text: "no running, no upper body" })).toBe("Operation · no running, no upper body");
    expect(bandText({ day: "2026-12-04", reason: "vacation", label: null, text: "everything off" })).toBe("Vacation");
  });

  it("round-trips an entry through the form, and has no body when nothing is off", () => {
    expect(formBody(formFromEntry(OPERATION))).toEqual({ reason: "injury", label: "Operation", start: "2026-12-03", restrictions: OPERATION.restrictions });
    expect(formBody({ ...formFromEntry(OPERATION), until: { run: "", bike: "", swim: "", upper: "", core: "", lower: "" } })).toBeNull();
  });
});
