// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Plan as PlanData, PlanItem } from "../lib/plan";
import Plan from "./Plan";

const item = (over: Partial<PlanItem>): PlanItem => ({
  id: "r1", exercise: "Bench Press (Barbell)", equipment: "barbell", kind: "routine", muscle: "mid_lower_chest",
  sets: 3, reps: "8–12", weight_kg: 80, dumbbell: null, change: "same", estimate: false,
  last: [{ kg: 80, reps: 8 }], replaces: null, reason: null, goal: "Bench 100 kg", skipped: false, suggested: false, ...over,
});
const PLAN: PlanData = {
  id: 7, day: "Chest - Schouders - Triceps", built_on: "2026-10-26", comeback: false,
  items: [item({}), item({ id: "a1", exercise: "Face Pull", kind: "add", muscle: "rear_delt", suggested: true,
    change: "new", estimate: true, weight_kg: 15, last: [], reason: "Rear delts: 1.5 sets/week, aim for 4–12", goal: null })],
};
const DAYS = { days: [{ title: "Chest - Schouders - Triceps", last_done: "2026-10-24", exercise_count: 7 },
  { title: "Rug - Bicep", last_done: "2026-10-21", exercise_count: 6 }], missed_available: true, comeback: false, goals: [] };

const apiFetch = vi.fn((path: string, init?: RequestInit) => {
  if (path.startsWith("/api/plan/days")) return Promise.resolve(DAYS);
  if (path.startsWith("/api/preferences")) return Promise.resolve({ avoid_muscles: [], never_exercises: [], coach_notes: "" });
  if (path.startsWith("/api/muscles")) return Promise.resolve([]);
  if (init?.method === "POST") return Promise.resolve(PLAN);
  return Promise.resolve(PLAN);
});
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));

afterEach(() => { cleanup(); apiFetch.mockClear(); });

const open = async (entry = "/plan") => render(<MemoryRouter initialEntries={[entry]}><Plan /></MemoryRouter>);

describe("Plan page", () => {
  it("lists your Hevy routines by their own names", async () => {
    await open();
    expect(await screen.findByRole("button", { name: /Chest - Schouders - Triceps/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Rug - Bicep/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Just what I've missed/ })).toBeTruthy();
  });

  it("shows the plan with extras in their own block and the goal on the lift", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Bench Press (Barbell)");
    const extra = screen.getByRole("region", { name: "Extra, if you have time" });
    expect(within(extra).getByText("Face Pull")).toBeTruthy();
    expect(screen.getByText(/Goal: Bench 100 kg/)).toBeTruthy();
    expect(screen.getByText("last: 80×8")).toBeTruthy();
  });

  it("offers 'don't suggest again' only on suggested exercises", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Bench Press (Barbell)");
    fireEvent.click(screen.getByRole("button", { name: "More for Bench Press (Barbell)" }));
    expect(screen.queryByRole("menuitem", { name: "Don't suggest this again" })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "Skip for today" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "More for Face Pull" }));
    expect(screen.getByRole("menuitem", { name: "Don't suggest this again" })).toBeTruthy();
  });

  it("swaps an item by its id", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Face Pull");
    fireEvent.click(screen.getByRole("button", { name: "Swap Face Pull" }));
    expect(apiFetch).toHaveBeenCalledWith("/api/plan/7/items/a1/swap", { method: "POST" });
  });

  it("keeps the menu usable on phones, where tapping an item blurs without focusing it", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Face Pull");
    fireEvent.click(screen.getByRole("button", { name: "More for Face Pull" }));
    const never = screen.getByRole("menuitem", { name: "Don't suggest this again" });
    fireEvent.blur(screen.getByRole("menuitem", { name: "Skip for today" }), { relatedTarget: null });
    fireEvent.click(never);
    expect(apiFetch).toHaveBeenCalledWith("/api/plan/7/items/a1/never", { method: "POST" });
  });

  it("closes the menu when tapping elsewhere", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Face Pull");
    fireEvent.click(screen.getByRole("button", { name: "More for Face Pull" }));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
