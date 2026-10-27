// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Profile } from "../lib/types";
import Body from "./Body";

let profile: Profile = { date_of_birth: null, height_cm: 182, sex: null, max_hr_override: null, ftp_override: null,
  resting_hr_override: null, dumbbell_weights: "pair", reminder_weeks: 2, reminder_hevy: true };
const apiFetch = vi.fn((path: string, init?: RequestInit): Promise<unknown> => {
  if (path === "/api/profile" && init?.method === "PATCH") {
    profile = { ...profile, ...JSON.parse(init.body as string) };
    return Promise.resolve(profile);
  }
  if (path === "/api/profile") return Promise.resolve(profile);
  if (path === "/api/checkins") return Promise.resolve([{ measured_on: "2026-10-20", values: { 1: 80.4 } }]);
  if (path === "/api/measurement-types") return Promise.resolve([{ id: 1, name: "Weight", unit: "kg", kind: "weight" }]);
  return Promise.resolve(null);
});
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  apiDownload: () => Promise.resolve("downloaded"),
}));
afterEach(() => { cleanup(); apiFetch.mockClear(); });

describe("Body", () => {
  it("updates the header and the next check-in date when the reminder changes", async () => {
    render(<Body />);
    expect(await screen.findByText("Last check-in 20 Oct 2026 · next on 3 Nov 2026")).toBeTruthy();
    expect(screen.getByText(/A check-in every 2 weeks/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Every 4 weeks" }));
    await waitFor(() => expect(screen.getByText(/A check-in every 4 weeks/)).toBeTruthy());
    expect(screen.getByText("Last check-in 20 Oct 2026 · next on 17 Nov 2026")).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledWith("/api/profile", { method: "PATCH", body: JSON.stringify({ reminder_weeks: 4 }) });
  });

  it("puts the reminder back when saving it fails", async () => {
    render(<Body />);
    await screen.findByText(/A check-in every/);
    apiFetch.mockImplementationOnce(() => Promise.reject(new Error("Server's down")));
    fireEvent.click(screen.getByRole("button", { name: "Every week" }));
    expect(await screen.findByText("Server's down")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Every week" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByText(/A check-in every week\./)).toBeNull();
  });
});
