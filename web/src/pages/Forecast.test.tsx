// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { aheadLine, type Forecast as ForecastData, type GoalForecast, goalTick, goalValue } from "../lib/forecast";
import Forecast from "./Forecast";

let reply: () => Promise<unknown> = () => Promise.resolve(null);
vi.mock("../lib/api", () => {
  class ApiError extends Error { constructor(public status: number, public detail: string) { super(detail); } }
  return { ApiError, apiFetch: (path: string) => (path === "/api/forecast" ? reply() : Promise.reject(new Error(`unexpected ${path}`))) };
});
// jsdom has no layout: give the charts a fixed size so their SVG (reference-line labels and all) renders.
vi.mock("recharts", async (original) => ({
  ...(await original<typeof import("recharts")>()),
  ResponsiveContainer: ({ children }: { children: ReactElement }) => cloneElement(children, { width: 400, height: 200 } as never),
}));
beforeAll(() => {
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined })) as never;
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as never;
});
afterEach(cleanup);

const weekly = (start: string, values: number[]) => values.map((v, n): [string, number] =>
  [new Date(Date.UTC(+start.slice(0, 4), +start.slice(5, 7) - 1, +start.slice(8) + 7 * n)).toISOString().slice(0, 10), v]);

const BENCH: GoalForecast = {
  goal_id: 1, text: "Bench 100 kg", kind: "lift", unit: "kg", lower_is_better: false, target: 100, current: 96.5,
  deadline: "2027-03-01", history: weekly("2026-09-07", [90, 92.5, 94, 95, 96.5]),
  projection: [["2026-10-12", 96.5, 96.5, 96.5], ["2026-10-19", 97.4, 96.8, 98], ["2026-12-28", 100, 98, 102.5]],
  eta: { likely: "2027-01-15", early: "2026-12-20", late: "2027-02-20" }, status: "on_track",
  summary: "Around mid-January (likely Dec–Feb), before your deadline",
};
const FIVE_K: GoalForecast = {
  goal_id: 2, text: "Run 5k under 25 min", kind: "time", unit: "min", lower_is_better: true, target: 25, current: 26.5,
  deadline: null, history: weekly("2026-09-14", [28, 27.25, 26.5]), projection: [["2026-09-28", 26.5, 26.5, 26.5], ["2026-11-23", 25, 24.5, 25.8]],
  eta: { likely: "2026-11-23", early: null, late: null }, status: "eta", summary: "Around late November at this pace",
};
const SQUAT: GoalForecast = {
  goal_id: 3, text: "Squat 140 kg", kind: "lift", unit: "kg", lower_is_better: false, target: 140, current: 120, deadline: "2027-06-01",
  history: [["2026-10-19", 120]], projection: [], eta: null, status: "too_little_data", summary: "A few more weeks of squats and this can say when",
};
const days = [
  ...Array.from({ length: 28 }, (_, n) => ({ day: `2026-${n < 2 ? "09" : "10"}-${String(n < 2 ? 29 + n : n - 1).padStart(2, "0")}`,
    fitness: 30 + n / 4, fatigue: 34, form: -4, planned: false })),
  ...Array.from({ length: 14 }, (_, n) => ({ day: n < 5 ? `2026-10-${27 + n}` : `2026-11-${String(n - 4).padStart(2, "0")}`,
    fitness: 38.2 + n * 0.3, fatigue: 36 - n, form: n === 13 ? 6.2 : 0, planned: true })),
];
const RACE: NonNullable<ForecastData["race"]> = {
  predictions: [
    { name: "5k", km: 5, seconds: 1450, from: { activity_id: 812, day: "2026-10-20", km: 8.2, seconds: 2460 } },
    { name: "10k", km: 10, seconds: 3020, from: { activity_id: 812, day: "2026-10-20", km: 8.2, seconds: 2460 } },
    { name: "Half marathon", km: 21.0975, seconds: 6720, from: { activity_id: 812, day: "2026-10-20", km: 8.2, seconds: 2460 } },
  ],
  history: weekly("2026-09-01", [1530, 1500, 1470, 1450]),
  note: "From your best recent run; holds if you train for the distance.",
};
const FTP: NonNullable<ForecastData["ftp"]> = {
  now: 251, source: "zwift", history: [["2026-08-01", 238], ["2026-09-15", 245], ["2026-10-20", 251]],
  projection: [["2026-10-20", 251, 251, 251], ["2026-12-15", 260, 254, 266]], summary: "Around 260 W by mid-December",
};
const OPERATION = { start: "2026-10-05", end: "2026-10-16", reason: "injury" as const, label: "Operation" };
const FULL: ForecastData = { goals: [BENCH, FIVE_K, SQUAT], race: RACE, fitness: { days }, ftp: FTP, time_off: [] };

const open = (data: ForecastData | Error) => {
  reply = () => (data instanceof Error ? Promise.reject(data) : Promise.resolve(data));
  return render(<MemoryRouter><Forecast /></MemoryRouter>);
};
const card = async (title: string) => (await screen.findByRole("heading", { name: title })).closest("section") as HTMLElement;

describe("Forecast", () => {
  it("shows a goal on track with its summary, chip, target line and deadline", async () => {
    open(FULL);
    const c = within(await card("Bench 100 kg"));
    expect(c.getByText("On track").className).toContain("pill goal");
    expect(c.getByText("Around mid-January (likely Dec–Feb), before your deadline")).toBeTruthy();
    expect(c.getByText(/Now 96.5 kg · target 100 kg/).textContent).toBe("Now 96.5 kg · target 100 kg by 1 Mar 2027");
    expect(c.getByRole("img", { name: /deadline 1 Mar 2027/ })).toBeTruthy();
    expect(c.getByText("Target 100 kg")).toBeTruthy();
    expect(c.getAllByText("1 Mar").length).toBeGreaterThan(0);
    expect(c.getByText("Likely")).toBeTruthy();
  });

  it("writes a time goal (lower is better) in m:ss and doesn't call it up", async () => {
    open(FULL);
    const c = within(await card("Run 5k under 25 min"));
    expect(c.getByText("No date yet")).toBeTruthy();
    expect(c.getByText("Now 26:30 · target 25:00")).toBeTruthy();
    expect(c.getByText("Target 25:00")).toBeTruthy();
    expect(c.getByRole("img", { name: /lower is better/ })).toBeTruthy();
    expect(c.queryByText(/\bup\b/i)).toBeNull();
    expect(goalTick(95.5, "min")).toBe("1:35:30");
    expect(goalValue(102.5, "kg")).toBe("102.5 kg");
    expect(goalValue(250.4, "W")).toBe("250 W");
  });

  it("shows only the summary and the points so far when there's too little data", async () => {
    open(FULL);
    const c = within(await card("Squat 140 kg"));
    expect(c.getByText("Too little data")).toBeTruthy();
    expect(c.getByText("A few more weeks of squats and this can say when")).toBeTruthy();
    expect(c.queryByText("Likely")).toBeNull();
    expect(c.queryByText(/^Target/)).toBeNull();
  });

  it("points to the coach when there are no goals, and leaves out FTP when there's none", async () => {
    open({ goals: [], race: null, fitness: null, ftp: null, time_off: [] });
    const line = await screen.findByText((_, el) => el?.tagName === "P" && el.textContent === "Set a goal with the coach and its forecast shows here.");
    expect(within(line).getByRole("link", { name: "coach" }).getAttribute("href")).toBe("/coach");
    expect(screen.queryByRole("heading", { name: "FTP" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Race times" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Fitness ahead" })).toBeNull();
  });

  it("shows race times with pace and the run they're from", async () => {
    open(FULL);
    const c = within(await card("Race times"));
    const tiles = [...document.querySelectorAll(".tiles .tile")].map((t) => [...t.children].map((e) => e.textContent));
    expect(tiles).toEqual([["5k", "24:10", "4:50 /km"], ["10k", "50:20", "5:02 /km"], ["Half marathon", "1:52:00", "5:19 /km"]]);
    const from = c.getByRole("link", { name: "your 8.2 km run on 20 Oct" });
    expect(from.getAttribute("href")).toBe("/activities/812");
    expect(from.parentElement?.textContent).toBe("from your 8.2 km run on 20 Oct");
    expect(c.getByText("Predicted 5k")).toBeTruthy();
    expect(c.getByText(RACE.note)).toBeTruthy();
  });

  it("says where fitness goes if you do the planned weeks", async () => {
    open(FULL);
    expect(await screen.findByText("Do your planned two weeks and fitness goes 38 → 42; form on Mon 9 Nov: +6 (fresh)")).toBeTruthy();
    expect(within(await card("Fitness ahead")).getByText("Today")).toBeTruthy();
    expect(aheadLine(days.filter((d) => !d.planned))).toBeNull();
    expect(aheadLine(days.slice(-7).map((d) => ({ ...d, form: -12 })))).toBe("Do your planned week and fitness goes 40 → 42; form on Mon 9 Nov: −12 (building)");
  });

  it("shows today's FTP with its source and summary", async () => {
    open(FULL);
    const c = within(await card("FTP"));
    expect(c.getByText("251 W")).toBeTruthy();
    expect(c.getByText("Now · from Zwift")).toBeTruthy();
    expect(c.getByText("Around 260 W by mid-December")).toBeTruthy();
  });

  it("shades time off on the goal, fitness and FTP charts and says what the shading is", async () => {
    open({ ...FULL, time_off: [OPERATION] });
    expect(await screen.findByText("Shaded stretches are time off.")).toBeTruthy();
    expect(within(await card("Bench 100 kg")).getByRole("img").querySelectorAll(".recharts-reference-area").length).toBe(1);
    expect(within(await card("Fitness ahead")).getAllByRole("img")[0].querySelectorAll(".recharts-reference-area").length).toBe(1);
    expect(within(await card("FTP")).getByRole("img").querySelectorAll(".recharts-reference-area").length).toBe(1);
  });

  it("shades nothing without time off", async () => {
    open(FULL);
    await card("FTP");
    expect(document.querySelector(".recharts-reference-area")).toBeNull();
    expect(screen.queryByText("Shaded stretches are time off.")).toBeNull();
  });

  it("keeps a failed request to one quiet line", async () => {
    open(new Error("offline"));
    expect(await screen.findByText("The forecast isn't available right now.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Goals" })).toBeNull();
  });
});
