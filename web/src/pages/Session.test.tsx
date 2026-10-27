// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionDetail } from "../lib/session";
import Session from "./Session";

const base = {
  id: 2, day: "2026-10-29", sport: "bike" as const, title: "Sweet Spot 3x10", note: "Seated", optional: false, routine: null,
  zwift: { blocks: [], duration_s: 3900, summary: "65′ · 3 × 10′ at 151 W", filename: "2026-10-29 Sweet Spot 3x10.zwo" },
  zwift_status: "synced" as const, sort: 0, source: "coach" as const, done: false, activity_id: null, targets: null,
  goal_id: 1, goal: "FTP 200 W", result: null,
};
const parts = [
  { label: "Warm-up", start_s: 0, end_s: 600, from_w: 84, to_w: 126, from_frac: 0.5, to_frac: 0.75, work: false },
  { label: "Interval 1", start_s: 600, end_s: 1200, from_w: 151, to_w: 151, from_frac: 0.9, to_frac: 0.9, work: true },
];
const BEFORE: SessionDetail = { item: base, plan: { kind: "zwift", ftp: 168, ftp_is_set: true, parts, duration_s: 3900, sweet_spot_min: 30, tss_est: 58 }, actual: null };
const AFTER: SessionDetail = {
  item: { ...base, done: true, activity_id: 29, result: "Done · 65′ · 128 W · intervals on target" },
  plan: BEFORE.plan,
  actual: { activity_id: 29, start_at: "2026-10-29T07:12:00+01:00", duration_s: 3900, moving_s: 3900, distance_m: null, avg_power: 128,
    np: 140, tss: 60, avg_hr: 146, avg_pace_s_per_km: null, swim_pace_s_per_100m: null, swim_lengths: null, swim_strokes: null,
    power: [[0, 90], [600, 151]], hr: [[0, 120], [600, 150]],
    parts: [{ label: "Interval 1", target_w: 151, avg_w: 150, avg_hr: 152, avg_cadence: 88, status: "on_target" }], intervals_on_target: true },
};
const GYM: SessionDetail = {
  item: { ...base, sport: "gym", title: "Push", routine: "Push", zwift: null, zwift_status: null, done: true, activity_id: 30, goal: null },
  plan: { kind: "gym", routine: "Push", items: [] },
  actual: { activity_id: 30, start_at: "2026-10-29T18:00:00+01:00", duration_s: 3600, moving_s: 3600, distance_m: null, avg_power: null,
    np: null, tss: null, avg_hr: null, avg_pace_s_per_km: null, swim_pace_s_per_100m: null, swim_lengths: null, swim_strokes: null,
    rows: [{ exercise: "Face Pull", planned: { sets: 3, reps: "8–12", weight_kg: 15, dumbbell: null }, done: [], status: "skipped_by_you", extra: true, goal: null }] },
};

let reply: SessionDetail = BEFORE;
const apiFetch = vi.fn((path: string, _init?: RequestInit) => Promise.resolve(path.endsWith("/detail") ? reply : {}));
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));
afterEach(() => { cleanup(); apiFetch.mockClear(); });
const open = (d: SessionDetail) => {
  reply = d;
  render(<MemoryRouter initialEntries={["/agenda/2"]}><Routes><Route path="/agenda/:id" element={<Session />} /></Routes></MemoryRouter>);
};

describe("Session page", () => {
  it("shows the plan's parts before the ride", async () => {
    open(BEFORE);
    await screen.findByRole("heading", { name: "Sweet Spot 3x10" });
    expect(screen.getByText("Interval 1")).toBeTruthy();
    expect(screen.getByText("for your goal: FTP 200 W")).toBeTruthy();
    expect(screen.getByText(/In Zwift ✓/)).toBeTruthy();
  });

  it("shows how it went afterwards", async () => {
    open(AFTER);
    await screen.findByRole("heading", { name: "Sweet Spot 3x10" });
    const table = screen.getByRole("table", { name: "Interval by interval" });
    expect(within(table).getByText("On target")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Full activity/ }).getAttribute("href")).toBe("/activities/29");
  });

  it("says skipped by you for a gym extra you skipped", async () => {
    open(GYM);
    await screen.findByRole("heading", { name: "Push" });
    expect(screen.getByText("Skipped by you")).toBeTruthy();
  });

  it("moves the session to another day", async () => {
    open(BEFORE);
    await screen.findByRole("heading", { name: "Sweet Spot 3x10" });
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2026-10-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/api/agenda/2", { method: "PATCH", body: JSON.stringify({ day: "2026-10-31" }) }));
  });

  it("asks before deleting", async () => {
    open(BEFORE);
    await screen.findByRole("heading", { name: "Sweet Spot 3x10" });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(apiFetch).not.toHaveBeenCalledWith("/api/agenda/2", { method: "DELETE" });
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete it" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/api/agenda/2", { method: "DELETE" }));
  });

  it("reads comma decimals and leaves untouched targets alone", async () => {
    open({ item: { ...base, sport: "run", title: "Steady run", zwift: null, zwift_status: null,
      targets: { pace_low: 335, distance_m: 8000, pace_high: 350 } }, plan: { kind: "targets", hr_bpm: null }, actual: null });
    await screen.findByRole("heading", { name: "Steady run" });
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Steady run 8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/api/agenda/2", { method: "PATCH", body: JSON.stringify({ title: "Steady run 8" }) }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Distance (km)"), { target: { value: "8,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const body = JSON.parse(apiFetch.mock.calls.filter((c) => c[1]?.method === "PATCH").at(-1)![1]!.body as string);
      expect(body.targets.distance_m).toBe(8500);
    });
  });

  it("labels the power axis and counts intervals on target", async () => {
    open({ ...AFTER, actual: { ...AFTER.actual!, parts: [...AFTER.actual!.parts!,
      { label: "Interval 2", target_w: 151, avg_w: 140, avg_hr: 155, avg_cadence: 86, status: "below" }] } });
    await screen.findByRole("heading", { name: "Sweet Spot 3x10" });
    const chart = screen.getByRole("group", { name: "Power over the ride" });
    expect(within(chart).getByText("150 W")).toBeTruthy();
    expect(screen.getByText("1 of 2 on target")).toBeTruthy();
  });

  it("labels the pace axis with the target band", async () => {
    open({ item: { ...base, sport: "run", title: "Steady run", zwift: null, zwift_status: null, done: true, activity_id: 31,
        targets: { pace_low: 335, pace_high: 350 } },
      plan: { kind: "targets", pace_low: 335, pace_high: 350, hr_bpm: null },
      actual: { ...AFTER.actual!, power: undefined, parts: undefined, pace: [[0, 340], [600, 345]], splits: null, zones: null } });
    await screen.findByRole("heading", { name: "Steady run" });
    const chart = screen.getByRole("group", { name: "Pace over the run" });
    expect(within(chart).getByText("5:35")).toBeTruthy();
    expect(within(chart).getByText("5:50")).toBeTruthy();
  });

  it("doesn't offer to plan a gym day that's already done", async () => {
    open({ ...GYM, plan: { kind: "gym", routine: "Push", items: [{ id: "x", exercise: "Face Pull", equipment: "cable", kind: "add",
      muscle: "rear_delt", sets: 3, reps: "8–12", weight_kg: 15, dumbbell: null, change: null, estimate: false, last: [],
      replaces: null, reason: null, goal: null, skipped: true, suggested: true }] } });
    await screen.findByRole("heading", { name: "Push" });
    expect(screen.queryByRole("link", { name: "Plan it" })).toBeNull();
  });

  it("shows a lift planned twice as two rows", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const row = { exercise: "Bench Press (Barbell)", planned: { sets: 3, reps: "8–12", weight_kg: 80, dumbbell: null },
      done: [{ kg: 80, reps: 8 }], status: "close" as const, extra: false, goal: null };
    open({ ...GYM, actual: { ...GYM.actual!, rows: [row, { ...row, planned: { ...row.planned, weight_kg: 60 } }] } });
    await screen.findByRole("heading", { name: "Push" });
    expect(screen.getAllByText("Bench Press (Barbell)")).toHaveLength(2);
    expect(errors.mock.calls.some((c) => String(c[0]).includes("same key"))).toBe(false);
    errors.mockRestore();
  });

  it("keeps a done rest day's note next to what you did", async () => {
    open({ item: { ...base, sport: "rest", title: "Rest", note: "Optional: easy 20–30 min spin under 126 W", zwift: null, zwift_status: null,
        done: true, activity_id: 40, result: "Done · 30′ · 88 W", goal: null },
      plan: { kind: "note" }, actual: { ...AFTER.actual!, activity_id: 40, parts: undefined } });
    await screen.findByRole("heading", { name: "Rest" });
    expect(screen.getByText("Done · 30′ · 88 W")).toBeTruthy();
    expect(screen.getByText("Optional: easy 20–30 min spin under 126 W")).toBeTruthy();
  });
});
