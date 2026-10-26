// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgendaItem, AgendaWeek } from "../lib/agenda";
import Agenda from "./Agenda";

const item = (over: Partial<AgendaItem>): AgendaItem => ({
  id: 1, day: "2026-10-27", sport: "gym", title: "Rug - Bicep", note: null, optional: false, routine: "Rug - Bicep",
  zwift: null, zwift_status: null, sort: 0, source: "coach", done: false, activity_id: null, ...over,
});
const WEEK: AgendaWeek = {
  week_start: "2026-10-26", today: "2026-10-26",
  items: [
    item({}),
    item({ id: 2, day: "2026-10-29", sport: "bike", title: "Sweet Spot 3x10", routine: null, zwift_status: "pending",
      zwift: { blocks: [{ type: "steady", duration_s: 600, power: 0.9 }], duration_s: 600, summary: "10′ · 10′ at 151 W",
        filename: "2026-10-29 Sweet Spot 3x10.zwo" } }),
  ],
};

const apiFetch = vi.fn((path: string, _init?: RequestInit) => {
  if (path.startsWith("/api/plan/days")) return Promise.resolve({ days: [{ title: "Rug - Bicep", last_done: "2026-10-21", exercise_count: 6 }], missed_available: true, comeback: false, goals: [] });
  return Promise.resolve(WEEK);
});
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));
afterEach(() => { cleanup(); apiFetch.mockClear(); });

const open = async () => {
  render(<MemoryRouter initialEntries={["/agenda?week=2026-10-26"]}><Agenda /></MemoryRouter>);
  await screen.findByText("Sweet Spot 3x10");
};

describe("Agenda page", () => {
  it("shows the week with gym days linking to the planner", async () => {
    await open();
    expect(screen.getAllByRole("region", { name: /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) / })).toHaveLength(7);
    const link = screen.getByRole("link", { name: /Plan it/ });
    expect(link.getAttribute("href")).toBe("/plan?day=Rug%20-%20Bicep");
    expect(screen.getByText("Goes to Zwift at the next sync")).toBeTruthy();
  });

  it("adds a run on Wednesday", async () => {
    await open();
    const wed = screen.getByRole("region", { name: /^Wed / });
    fireEvent.click(within(wed).getByRole("button", { name: "Add to Wednesday" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("What"), { target: { value: "run" } });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Easy run 30′" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/api/agenda", expect.objectContaining({ method: "POST" })));
    const body = JSON.parse((apiFetch.mock.calls.find((c) => c[1]?.method === "POST")![1] as RequestInit).body as string);
    expect(body).toEqual({ day: "2026-10-28", sport: "run", title: "Easy run 30′", note: null, optional: false, routine: null });
  });

  it("moves an item to another day", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: /Sweet Spot 3x10/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Day"), { target: { value: "2026-10-30" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/api/agenda/2", { method: "PATCH", body: JSON.stringify({ day: "2026-10-30" }) }));
  });

  it("asks before deleting", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: /Sweet Spot 3x10/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(apiFetch).not.toHaveBeenCalledWith("/api/agenda/2", { method: "DELETE" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Yes, delete it" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/api/agenda/2", { method: "DELETE" }));
  });
});
