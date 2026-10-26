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
});
