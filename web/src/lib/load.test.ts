import { describe, expect, it } from "vitest";
import { formNumber, formWords } from "./load";

describe("training load words", () => {
  it("says what today's form means", () => {
    expect(formWords(-25)).toBe("Very tired, ease off");
    expect(formWords(-20)).toBe("Building");
    expect(formWords(-10.3)).toBe("Building");
    expect(formWords(-10)).toBe("Steady");
    expect(formWords(5)).toBe("Steady");
    expect(formWords(5.4)).toBe("Fresh");
  });
  it("signs form", () => {
    expect(formNumber(7.6)).toBe("+8");
    expect(formNumber(-10.3)).toBe("−10");
    expect(formNumber(0.2)).toBe("0");
  });
});
