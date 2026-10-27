// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Plan as PlanData, PlanItem } from "../lib/plan";
import { ApiError } from "../lib/api";
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

const apiFetch = vi.fn((path: string, init?: RequestInit): Promise<unknown> => {
  if (path.startsWith("/api/plan/days")) return Promise.resolve(DAYS);
  if (path.startsWith("/api/preferences")) return Promise.resolve({ avoid_muscles: [], never_exercises: [], coach_notes: "" });
  if (path.startsWith("/api/muscles")) return Promise.resolve([]);
  if (init?.method === "POST") return Promise.resolve(PLAN);
  return Promise.resolve(PLAN);
});
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  ApiError: class ApiError extends Error { constructor(public status: number, public detail: string) { super(detail); } },
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

  it("hides Swap for an exercise the app can't find alternatives for", async () => {
    PLAN.items.push(item({ id: "u1", exercise: "Mystery Machine", muscle: null }));
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Mystery Machine");
    expect(screen.queryByRole("button", { name: "Swap Mystery Machine" })).toBeNull();
    PLAN.items.pop();
  });

  it("moves through the menu with arrow keys and gives focus back", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Face Pull");
    const more = screen.getByRole("button", { name: "More for Face Pull" });
    fireEvent.click(more);
    const items = screen.getAllByRole("menuitem");
    await waitFor(() => expect(document.activeElement).toBe(items[0]));
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(document.activeElement).toBe(more);
  });

  it("says so when there's nothing missed to plan", async () => {
    const empty = { ...PLAN, day: null, items: [] };
    apiFetch.mockImplementationOnce(() => Promise.resolve(empty));
    await open("/plan?missed=1");
    expect(await screen.findByText(/Nothing stands out/)).toBeTruthy();
  });

  it("comes back to the missed plan after Preferences", async () => {
    await open("/plan?missed=1");
    await screen.findByText("Face Pull");
    fireEvent.click(screen.getByRole("button", { name: "Preferences" }));
    fireEvent.click(await screen.findByRole("button", { name: "‹ Back" }));
    await screen.findByText("Face Pull");
    expect(apiFetch).toHaveBeenLastCalledWith("/api/plan", { signal: expect.any(AbortSignal) });
  });

  it("reloads the plan when an item is gone", async () => {
    await open("/plan?day=Chest%20-%20Schouders%20-%20Triceps");
    await screen.findByText("Face Pull");
    apiFetch.mockImplementationOnce(() => Promise.reject(new ApiError(404, "Not found")));
    fireEvent.click(screen.getByRole("button", { name: "Swap Face Pull" }));
    await waitFor(() => expect(apiFetch).toHaveBeenLastCalledWith("/api/plan?day=Chest%20-%20Schouders%20-%20Triceps", { signal: expect.any(AbortSignal) }));
    expect(await screen.findByText("Face Pull")).toBeTruthy();
  });

  it("says when the muscle list couldn't load in Preferences", async () => {
    apiFetch.mockImplementationOnce(() => Promise.resolve({ avoid_muscles: [], never_exercises: [], coach_notes: "" }))
      .mockImplementationOnce(() => Promise.reject(new Error("down")));
    await open("/plan?prefs=1");
    expect(await screen.findByText("Couldn't load the muscle list.")).toBeTruthy();
  });
});
