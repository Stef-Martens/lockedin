// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Profile } from "../lib/types";
import Body from "./Body";
import { ftpLine } from "./body/ProfileCard";

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

  it("says where today's FTP comes from, with nothing to fill in", async () => {
    profile = { ...profile, ftp_now: { w: 157, source: "zwift", since: "2026-10-17" } };
    render(<Body />);
    expect(await screen.findByText("157 W from Zwift (since 17 Oct)")).toBeTruthy();
    expect((screen.getByLabelText("FTP (W)") as HTMLInputElement).placeholder).toBe("157 from Zwift");
  });

  it("names an estimate without a date", () => {
    expect(ftpLine({ w: 150, source: "estimate", since: null })).toBe("150 W estimated from your rides");
    expect(ftpLine({ w: 170, source: "owner", since: "2026-10-20" })).toBe("170 W entered by you (since 20 Oct)");
  });
});
