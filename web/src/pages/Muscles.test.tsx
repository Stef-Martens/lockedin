// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MapMuscle, MuscleMap } from "../lib/types";
import Muscles, { placeTip } from "./Muscles";

const muscle = (key: string, name: string, sets = 0, over: Partial<MapMuscle> = {}): MapMuscle => ({
  key, name, region: "x", target_low: 4, target_high: 14, sets, days: [], history: [], last_trained: null,
  lift: null, cardio: [], suggestion: null, ...over,
});
const MAP: MuscleMap = {
  week_start: "2026-10-19", is_current: false, first_week: "2026-09-14", trained_count: 1,
  cardio: [{ sport: "bike", minutes: 46, days: ["2026-10-25"] }],
  muscles: [muscle("triceps", "Triceps", 17), muscle("quads", "Quads", 0, { cardio: [{ sport: "bike", minutes: 46 }] }),
    muscle("calves", "Calves")],
};

vi.mock("../lib/api", () => ({
  apiFetch: vi.fn(() => Promise.resolve(MAP)),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));

afterEach(cleanup);

const renderPage = async () => {
  render(<MemoryRouter initialEntries={["/muscles?week=2026-10-19"]}><Muscles /></MemoryRouter>);
  await screen.findByText("Week of 19 Oct");
};
const chip = (name: string) => screen.getAllByRole("button", { name }).find((b) => b.classList.contains("chip"))!;
const shape = (key: string) => document.querySelector(`path[data-m="${key}"][tabindex="0"]`)!;

describe("Muscles page", () => {
  it("keeps the 'no gym work yet' chips while hovering and lets you pin from them", async () => {
    await renderPage();
    fireEvent.mouseEnter(chip("Calves"));
    expect(chip("Calves")).toBeTruthy();
    expect(chip("Quads")).toBeTruthy();
    fireEvent.click(chip("Calves"));
    expect(shape("calves").classList.contains("pinned")).toBe(true);
    expect(chip("Quads")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Calves" })).toBeTruthy();
  });

  it("still shows the hover panel for another muscle while one is pinned", async () => {
    await renderPage();
    fireEvent.click(shape("quads"));
    fireEvent.mouseMove(document.querySelector(".mm-figures")!, { clientX: 300, clientY: 300 });
    fireEvent.mouseEnter(shape("triceps"));
    expect(screen.getByRole("tooltip").textContent).toContain("Triceps");
  });

  it("shows the focused muscle's details even when another is pinned", async () => {
    await renderPage();
    fireEvent.click(shape("quads"));
    fireEvent.focus(shape("triceps"));
    expect(screen.getByRole("heading", { name: "Triceps" })).toBeTruthy();
  });
});

describe("placeTip", () => {
  const viewport = { w: 1440, h: 900 };
  it("sits below-right of the cursor when there's room", () => {
    expect(placeTip({ x: 100, y: 100 }, { w: 290, h: 300 }, viewport)).toEqual({ x: 118, y: 118 });
  });
  it("stays inside the screen at the right and bottom edges", () => {
    expect(placeTip({ x: 1400, y: 850 }, { w: 290, h: 420 }, viewport)).toEqual({ x: 1440 - 290 - 12, y: 900 - 420 - 12 });
  });
  it("never goes above the top when the panel is taller than the screen", () => {
    expect(placeTip({ x: 100, y: 600 }, { w: 290, h: 1000 }, viewport).y).toBe(12);
  });
});
