// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ActivitySummary } from "../lib/types";
import Activities from "./Activities";

/** Every request waits until the test answers it, so the order of answers is up to the test. */
interface Call { path: string; signal?: AbortSignal; resolve: (v: unknown) => void }
const calls: Call[] = [];
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => new Promise((resolve, reject) => {
    calls.push({ path, signal: init?.signal ?? undefined, resolve });
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  }),
}));
afterEach(() => { cleanup(); calls.length = 0; });

const activity = (id: number, sport: "bike" | "run", title: string): ActivitySummary => ({
  id, source: "healthfit", sport, sub_type: null, start_at: "2026-10-20T07:00:00Z", end_at: "2026-10-20T08:00:00Z",
  duration_s: 3600, moving_s: null, distance_m: null, elevation_m: null, avg_hr: null, max_hr: null, avg_power: null,
  max_power: null, avg_cadence: null, np: null, if_: null, tss: null, avg_pace_s_per_km: null, swim_pace_s_per_100m: null,
  calories: null, superseded_by: null, hr_merged_from: null, title, set_count: null,
});
const page = (items: ActivitySummary[], next: string | null = null) => ({ items, next_before: next });
const answer = async (match: (path: string) => boolean, value: unknown) => {
  const call = calls.find((c) => match(c.path) && !c.signal?.aborted);
  if (!call) throw new Error(`no open request matching ${match}`);
  await act(async () => { call.resolve(value); });
};
const open = () => render(<MemoryRouter initialEntries={["/activities"]}><Activities /></MemoryRouter>);

describe("Activities filters", () => {
  it("shows the filter you picked last, even when an earlier filter answers later", async () => {
    open();
    await answer((p) => !p.includes("sport="), page([activity(1, "bike", "Morning ride"), activity(2, "run", "Easy run")]));
    expect(screen.getByText("Morning ride")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Bike" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    const bike = calls.find((c) => c.path.includes("sport=bike"))!;
    expect(bike.signal?.aborted).toBe(true);  // leaving Bike cancelled its request

    await answer((p) => p.includes("sport=run"), page([activity(3, "run", "Tempo run")]));
    await act(async () => { bike.resolve(page([activity(4, "bike", "Late bike answer")])); });
    expect(screen.getByText("Tempo run")).toBeTruthy();
    expect(screen.queryByText("Late bike answer")).toBeNull();
    expect(screen.queryByText("Morning ride")).toBeNull();
  });

  it("drops a Load more that was still on its way when you switch filters", async () => {
    open();
    await answer((p) => !p.includes("sport="), page([activity(1, "bike", "Morning ride")], "2026-10-20T07:00:00Z"));
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    const more = calls.find((c) => c.path.includes("before="))!;
    expect(more.path).not.toContain("sport=");

    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(more.signal?.aborted).toBe(true);
    await answer((p) => p.includes("sport=run"), page([activity(3, "run", "Tempo run")]));
    await act(async () => { more.resolve(page([activity(5, "bike", "Older ride")])); });
    expect(screen.getByText("Tempo run")).toBeTruthy();
    expect(screen.queryByText("Older ride")).toBeNull();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("appends the next page under the same filter", async () => {
    open();
    await answer(() => true, page([activity(1, "bike", "Morning ride")], "2026-10-20T07:00:00Z"));
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await answer((p) => p.includes("before=2026-10-20T07%3A00%3A00Z"), page([activity(5, "bike", "Older ride")]));
    expect(screen.getByText("Morning ride")).toBeTruthy();
    expect(screen.getByText("Older ride")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });
});
