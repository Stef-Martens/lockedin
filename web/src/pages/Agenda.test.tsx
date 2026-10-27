// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Link, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgendaItem, AgendaWeek } from "../lib/agenda";
import Agenda from "./Agenda";

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({ ...(await orig<typeof import("react-router-dom")>()), useNavigate: () => navigate }));

const item = (over: Partial<AgendaItem>): AgendaItem => ({
  id: 1, day: "2026-10-27", sport: "gym", title: "Rug - Bicep", note: null, optional: false, routine: "Rug - Bicep",
  zwift: null, zwift_status: null, sort: 0, source: "coach", done: false, activity_id: null, targets: null, goal_id: null,
  goal: null, result: null, clash: null, plan_line: null, ...over,
});
const WEEK: AgendaWeek = {
  week_start: "2026-10-26", today: "2026-10-26", time_off: [],
  items: [
    item({ day: "2026-10-26", done: true, activity_id: 9, result: "Done · 52′", goal: "Bench 100 kg" }),
    item({ id: 2, day: "2026-10-29", sport: "bike", title: "Sweet Spot 3x10", routine: null, zwift_status: "pending",
      zwift: { blocks: [{ type: "steady", duration_s: 600, power: 0.9 }], duration_s: 600, summary: "10′ · 10′ at 151 W",
        filename: "2026-10-29 Sweet Spot 3x10.zwo" } }),
  ],
};

const apiFetch = vi.fn((path: string, _init?: RequestInit): Promise<unknown> => {
  if (path === "/api/time-off") return Promise.resolve([]);
  if (path.startsWith("/api/plan/days")) return Promise.resolve({ days: [{ title: "Rug - Bicep", last_done: "2026-10-21", exercise_count: 6 }], missed_available: true, comeback: false, goals: [] });
  return Promise.resolve(WEEK);
});
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));
afterEach(() => { cleanup(); apiFetch.mockClear(); });
// The Time off card asks for its own list; tests that swap the agenda's answer leave it empty.
const mock = (fn: (path: string, init?: RequestInit) => Promise<unknown>) =>
  apiFetch.mockImplementation((path, init) => (path === "/api/time-off" ? Promise.resolve([]) : fn(path, init)));

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

  it("shows a stepped run's plan line in place of its note", async () => {
    mock((path) => Promise.resolve(path === "/api/time-off" ? [] : { ...WEEK, items: [
      ...WEEK.items,
      item({ id: 5, day: "2026-10-28", sport: "run", title: "Intervals", note: "Keep it smooth", routine: null,
        plan_line: "10′ warm-up Z2 · 4 × (5′ @ 5:30–5:50, 2′ jog) · cool-down" }),
    ] }));
    await open();
    expect(screen.getByText("10′ warm-up Z2 · 4 × (5′ @ 5:30–5:50, 2′ jog) · cool-down")).toBeTruthy();
    expect(screen.queryByText("Keep it smooth")).toBeNull();
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

  it("shows done sessions with what you did, and opens a session page", async () => {
    await open();
    expect(screen.getByText("Done · 52′")).toBeTruthy();
    expect(screen.getByText("Bench 100 kg")).toBeTruthy();  // the goal it served stays visible once done
    fireEvent.click(screen.getByRole("button", { name: /Sweet Spot 3x10/ }));
    expect(navigate).toHaveBeenCalledWith("/agenda/2");
  });

  it("counts quick clicks on the week arrows from the URL", async () => {
    await open();
    mock(() => new Promise(() => undefined));  // the next weeks never arrive
    fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
    const asked = apiFetch.mock.calls.map((c) => c[0]);
    expect(asked).toContain("/api/agenda?week=2026-10-19");
    expect(asked).toContain("/api/agenda?week=2026-10-12");
    apiFetch.mockReset();
  });

  it("keeps the week asked for last when an older answer arrives late", async () => {
    let slow!: (w: AgendaWeek) => void;
    mock((path: string) => {
      if (path === "/api/agenda?week=2026-10-26") return new Promise((r) => { slow = r as (w: AgendaWeek) => void; });
      return Promise.resolve({ ...WEEK, week_start: "2026-11-02", items: [item({ id: 5, day: "2026-11-03", title: "Next week's ride", sport: "bike", routine: null })] });
    });
    render(<MemoryRouter initialEntries={["/agenda?week=2026-10-26"]}><Link to="/agenda?week=2026-11-02">go</Link><Agenda /></MemoryRouter>);
    fireEvent.click(screen.getByText("go"));
    await screen.findByText("Next week's ride");
    slow(WEEK);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("Sweet Spot 3x10")).toBeNull();
    expect(screen.getByText("Next week's ride")).toBeTruthy();
    apiFetch.mockReset();
  });

  it("clears an error when you move to another week", async () => {
    mock((path: string) => path === "/api/agenda?week=2026-10-19"
      ? Promise.reject(new Error("Server hiccup")) : Promise.resolve(WEEK));
    render(<MemoryRouter initialEntries={["/agenda?week=2026-10-19"]}><Link to="/agenda?week=2026-10-26">go</Link><Agenda /></MemoryRouter>);
    await screen.findByText("Server hiccup");
    fireEvent.click(screen.getByText("go"));
    expect(await screen.findByText("Sweet Spot 3x10")).toBeTruthy();
    apiFetch.mockReset();
  });

  it("drops the routine's name as title when you switch away from gym", async () => {
    mock((path: string) => path.startsWith("/api/plan/days")
      ? Promise.resolve({ days: [{ title: "Rug - Bicep", last_done: "2026-10-21", exercise_count: 6 }], missed_available: true, comeback: false, goals: [] })
      : Promise.resolve(WEEK));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Add to Wednesday" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect((within(dialog).getByLabelText("Title") as HTMLInputElement).value).toBe("Rug - Bicep"));
    fireEvent.change(within(dialog).getByLabelText("What"), { target: { value: "run" } });
    expect((within(dialog).getByLabelText("Title") as HTMLInputElement).value).toBe("");
    apiFetch.mockReset();
  });

  it("gives focus back to the + Add button when the sheet closes", async () => {
    mock((path: string) => path.startsWith("/api/plan/days")
      ? Promise.resolve({ days: [], missed_available: false, comeback: false, goals: [] }) : Promise.resolve(WEEK));
    await open();
    const add = screen.getByRole("button", { name: "Add to Wednesday" });
    add.focus();
    fireEvent.click(add);
    await screen.findByRole("dialog");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(add);
    apiFetch.mockReset();
  });

  it("shows a thin band on the days inside time off, and a clash in muted warning style", async () => {
    mock(() => Promise.resolve({ ...WEEK, time_off: [
        { day: "2026-10-28", reason: "injury", label: "Operation", text: "no running, no upper body" },
        { day: "2026-10-29", reason: "vacation", label: null, text: "everything off" }],
      items: [...WEEK.items, item({ id: 6, day: "2026-10-28", sport: "run", title: "Easy run", routine: null, clash: "Running is off until 17 Dec" })] }));
    await open();
    const wed = screen.getByRole("region", { name: /^Wed / });
    expect(within(wed).getByText("Operation · no running, no upper body").className).toContain("agenda-band");
    expect(within(screen.getByRole("region", { name: /^Thu / })).getByText("Vacation")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: /^Tue / })).queryByText(/Operation|Vacation/)).toBeNull();
    expect(within(wed).getByText("Running is off until 17 Dec").className).toContain("clash");
    apiFetch.mockReset();
  });

  it("doesn't flag a done item as clashing", async () => {
    mock(() => Promise.resolve({ ...WEEK, items: [...WEEK.items, item({ id: 6, day: "2026-10-26", sport: "run", title: "Easy run", routine: null,
      done: true, activity_id: 4, result: "Done · 30′", clash: "Running is off until 17 Dec" })] }));
    await open();
    expect(within(screen.getByRole("region", { name: /^Mon / })).getByText("Easy run")).toBeTruthy();
    expect(screen.queryByText("Running is off until 17 Dec")).toBeNull();
    apiFetch.mockReset();
  });

  it("shows the clash of a manual add once", async () => {
    mock((_path: string, init?: RequestInit) => init?.method === "POST" ? Promise.resolve(item({ id: 9, day: "2026-10-28", sport: "run", routine: null, title: "Easy run 30′", clash: "Running is off until 17 Dec" }))
      : Promise.resolve(WEEK));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Add to Wednesday" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("What"), { target: { value: "run" } });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "Easy run 30′" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
    const status = await screen.findByRole("status");
    expect(within(status).getByText("Added. Running is off until 17 Dec")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add to Thursday" }));
    await screen.findByRole("dialog");
    expect(screen.queryByRole("status")).toBeNull();
    apiFetch.mockReset();
  });

  it("shows the Time off card above the week", async () => {
    mock(() => Promise.resolve(WEEK));
    await open();
    expect(await screen.findByRole("heading", { name: "Time off" })).toBeTruthy();
  });
});
