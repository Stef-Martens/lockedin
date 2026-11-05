// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ActivityDetail as Detail } from "../lib/types";
import ActivityDetail from "./ActivityDetail";

const RUN = {
  id: 9, source: "healthfit", sport: "run", sub_type: null, start_at: "2026-11-04T07:00:00Z", end_at: "2026-11-04T08:00:00Z",
  duration_s: 3600, moving_s: null, distance_m: 10000, elevation_m: null, avg_hr: null, max_hr: null, avg_power: null,
  max_power: null, avg_cadence: null, np: null, if_: null, tss: null, avg_pace_s_per_km: 360, swim_pace_s_per_100m: null,
  calories: null, superseded_by: null, hr_merged_from: null, title: "Morning run", set_count: null,
  pool_length_m: null, swim_lengths: null, swim_strokes: null, best_20m_power: null, streams: null, sets: null,
  superseded_by_summary: null, hr_merged_from_summary: null, duplicates: [],
} as Detail;

let verdict: () => Promise<unknown>;
vi.mock("../lib/api", () => ({
  apiFetch: (path: string) => path.startsWith("/api/verdicts/") ? verdict()
    : path.startsWith("/api/profile") ? Promise.resolve({}) : Promise.resolve(RUN),
}));
afterEach(cleanup);
const open = () => render(<MemoryRouter initialEntries={["/activities/9"]}><Routes>
  <Route path="activities/:id" element={<ActivityDetail />} /></Routes></MemoryRouter>);

describe("ActivityDetail", () => {
  it("shows the coach's verdict, without the Last workout header", async () => {
    verdict = () => Promise.resolve({ activity: null, verdict: { status: "done", label: "unplanned", text: "A steady hour." } });
    open();
    expect(await screen.findByText("A steady hour.")).toBeTruthy();
    expect(screen.getByText("Not planned")).toBeTruthy();
    expect(screen.queryByText("Last workout")).toBeNull();
  });

  it("shows the page and no card when the verdict route answers 404", async () => {
    verdict = () => Promise.reject(Object.assign(new Error("Workout not found"), { status: 404 }));
    open();
    expect(await screen.findByRole("heading", { name: "Morning run" })).toBeTruthy();
    expect(screen.queryByText("Not planned")).toBeNull();
    expect(screen.queryByText("The coach is looking at it…")).toBeNull();
  });
});
