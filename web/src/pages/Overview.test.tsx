// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Overview from "./Overview";

const zero = { time_s: 0, distance_m: 0, sessions: 0 };
const totals = { bike: zero, run: zero, swim: zero, gym: zero, other: zero };
const OVERVIEW = { totals: { week: totals, month: totals }, weekly: [], streak: 0, comeback: null, wins: [], plateaus: [],
  focus: [{ type: "session", sport: "run", kind: "steady", title: "Steady run 40′", detail: "40 min in zone 2", reason: "Builds toward it · toward: Run a 10K", goal: "Run a 10K" }],
  measure_due: false, last_tape_measurement_on: null, checkin_due: false, next_checkin_on: "2026-11-09", last_checkin_on: "2026-10-26",
  hevy_due: false, hevy_last_upload_at: null };
const item = { sport: "bike", note: null, optional: false, routine: null, zwift: null, zwift_status: null, sort: 0, source: "coach",
  activity_id: null, targets: null, goal_id: null, goal: null, result: null, done: false };
const AGENDA = { week_start: "2026-10-26", today: "2026-10-29", items: [
  { ...item, id: 1, day: "2026-10-29", title: "Sweet Spot 3x10", done: true, activity_id: 5, result: "Done · 66′ · 128 W", goal: "FTP 200 W" },
  { ...item, id: 2, day: "2026-10-29", sport: "gym", title: "Push", routine: "Push" },
  { ...item, id: 4, day: "2026-10-29", sport: "rest", title: "Stretch a bit" },
  { ...item, id: 3, day: "2026-10-30", sport: "rest", title: "Rest" },
] };
const GOALS = [{ id: 1, text: "Bench 100 kg", target: "by March 2027", progress: { label: "96 / 100 kg est. 1RM", fraction: 0.96 } }];

let failGoals = false;
let agenda: (path: string) => Promise<unknown> = () => Promise.resolve(AGENDA);
vi.mock("../lib/api", () => ({
  apiFetch: (path: string) => path.startsWith("/api/goals") && failGoals ? Promise.reject(new Error("down"))
    : path.startsWith("/api/agenda") ? agenda(path)
    : Promise.resolve(path.startsWith("/api/overview") ? OVERVIEW : GOALS),
}));
vi.mock("../components/WeeklyVolumeChart", () => ({ default: () => null }));
afterEach(() => { cleanup(); agenda = () => Promise.resolve(AGENDA); });

describe("Overview", () => {
  it("shows today's to-dos with what's done, goals with progress, and goal tags on tips", async () => {
    render(<MemoryRouter><Overview /></MemoryRouter>);
    expect(await screen.findByText("1 of 2 done")).toBeTruthy(); // the rest/other note can't be ticked, so it doesn't count
    expect(screen.getByText("Stretch a bit")).toBeTruthy();
    expect(screen.getByText("Done · 66′ · 128 W")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See how it went" }).getAttribute("href")).toBe("/agenda/1");
    expect(screen.getByRole("link", { name: "Plan it" }).getAttribute("href")).toBe("/plan?day=Push");
    expect(screen.getByText(/Next · Friday: Rest/)).toBeTruthy();
    expect(await screen.findByText("96 / 100 kg est. 1RM")).toBeTruthy();
    expect(screen.getByText("toward: Run a 10K")).toBeTruthy();
  });

  it("says when goals couldn't be loaded instead of 'no goals'", async () => {
    failGoals = true;
    render(<MemoryRouter><Overview /></MemoryRouter>);
    expect(await screen.findByText("Couldn't load your goals.")).toBeTruthy();
    failGoals = false;
  });

  it("says when today's plan couldn't be loaded", async () => {
    agenda = () => Promise.reject(new Error("down"));
    render(<MemoryRouter><Overview /></MemoryRouter>);
    expect(await screen.findByText("Couldn't load today's plan.")).toBeTruthy();
  });

  it("looks into next week for what's next on a Sunday", async () => {
    agenda = (path) => Promise.resolve(path.includes("week=2026-11-02")
      ? { week_start: "2026-11-02", today: "2026-11-01", items: [{ ...item, id: 9, day: "2026-11-03", sport: "run", title: "Easy run" }] }
      : { week_start: "2026-10-26", today: "2026-11-01", items: [{ ...item, id: 8, day: "2026-11-01", sport: "rest", title: "Rest" }] });
    render(<MemoryRouter><Overview /></MemoryRouter>);
    expect(await screen.findByText(/Next · Tuesday: Easy run/)).toBeTruthy();
  });
});
