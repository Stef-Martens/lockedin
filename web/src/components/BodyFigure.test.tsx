import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { MapMuscle } from "../lib/types";
import BodyFigure from "./BodyFigure";

const KEYS = ["upper_chest", "mid_lower_chest", "front_delt", "side_delt", "rear_delt", "triceps", "biceps", "forearms",
  "lats", "mid_back", "upper_back_traps", "lower_back", "abs", "obliques", "glutes", "quads", "hamstrings", "adductors",
  "abductors", "calves"];
const muscles: MapMuscle[] = KEYS.map((key) => ({
  key, name: key, region: "x", target_low: 4, target_high: 14, sets: key === "triceps" ? 17 : 0, days: [], history: [],
  last_trained: null, lift: null, cardio: key === "quads" ? [{ sport: "bike", minutes: 46 }] : [], suggestion: null,
}));
const html = (side: "front" | "back") => renderToStaticMarkup(
  <BodyFigure side={side} muscles={muscles} focused={null} pinned={null} onHover={() => undefined} onPin={() => undefined} />);
const keysIn = (markup: string) => new Set([...markup.matchAll(/data-m="([a-z_]+)"/g)].map((m) => m[1]));

describe("BodyFigure", () => {
  it("draws all 20 muscles across the two views", () => {
    const all = new Set([...keysIn(html("front")), ...keysIn(html("back"))]);
    expect([...all].sort()).toEqual([...KEYS].sort());
  });

  it("puts muscles on the right side of the body", () => {
    expect(keysIn(html("front")).has("lats")).toBe(false);
    expect(keysIn(html("back")).has("abs")).toBe(false);
    expect(keysIn(html("front")).has("quads") && keysIn(html("back")).has("hamstrings")).toBe(true);
  });

  it("colours by shade and stripes cardio", () => {
    const back = html("back");
    expect(back).toMatch(/data-m="triceps"[^>]*fill:var\(--muscle-3\)|fill:var\(--muscle-3\)[^>]*data-m="triceps"/);
    expect(html("front")).toMatch(/data-m="biceps"[^>]*fill:var\(--muscle-0\)|fill:var\(--muscle-0\)[^>]*data-m="biceps"/);
    expect(html("front")).toContain("<pattern");
  });

  it("makes each muscle reachable by keyboard once", () => {
    const front = html("front");
    expect((front.match(/data-m="quads"[^>]*tabindex="0"|tabindex="0"[^>]*data-m="quads"/g) ?? []).length).toBe(1);
    expect(front).toContain('aria-label="quads: 0 sets this week, 46 minutes on the bike"');
  });
});
