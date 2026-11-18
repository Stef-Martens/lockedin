// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MacStatus } from "../lib/types";
import MacCheck from "./MacCheck";

const NOW = new Date("2026-11-18T21:00:00Z");
const idle: MacStatus = {
  last_run_at: "2026-11-18T20:56:00+00:00", last_seen_at: "2026-11-18T20:59:30+00:00", last_run_uploaded: 0,
  last_run_errors: 0, check_requested_at: null, check_done_at: null, check_uploaded: null,
};
const asked = { ...idle, check_requested_at: "2026-11-18T21:00:00+00:00" };

const server = vi.hoisted(() => ({ mac: null as MacStatus | null, calls: [] as [string, RequestInit | undefined][] }));
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => {
    server.calls.push([path, init]);
    return Promise.resolve(path === "/api/status" ? { mac: server.mac } : server.mac);
  },
}));
afterEach(() => { cleanup(); vi.useRealTimers(); server.calls = []; });

async function press(answer: MacStatus) {
  server.mac = answer;
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check again" })); });
}

async function tick(ms = 5000) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

describe("MacCheck", () => {
  it("shows when the Mac last checked and the last workout", () => {
    vi.useFakeTimers({ now: NOW, toFake: ["Date"] });
    render(<MacCheck mac={idle} lastWorkout="2026-11-18T18:00:00+00:00" />);
    expect(screen.getByText("Checked 4 min ago")).toBeTruthy();
    expect(screen.getByText(/Last workout 3 h ago/)).toBeTruthy();
  });

  it("asks the Mac to check, waits, then says what it found", async () => {
    vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    render(<MacCheck mac={idle} lastWorkout={null} />);
    await press(asked);
    expect(server.calls[0]).toEqual(["/api/sync/mac/check", { method: "POST" }]);
    expect(screen.getByText("Waiting for your Mac…")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Check again" }) as HTMLButtonElement).disabled).toBe(true);
    server.mac = { ...asked, check_done_at: "2026-11-18T21:01:10+00:00", check_uploaded: 1 };
    await tick();
    expect(screen.getByText("Done · 1 new workout")).toBeTruthy();
    const polls = server.calls.length;
    await tick(20000);
    expect(server.calls.length).toBe(polls); // stops asking once done
  });

  it("says nothing new when the check found nothing", async () => {
    vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    render(<MacCheck mac={idle} lastWorkout={null} />);
    await press(asked);
    server.mac = { ...asked, check_done_at: "2026-11-18T21:01:10+00:00", check_uploaded: 0 };
    await tick();
    expect(screen.getByText("Done · nothing new")).toBeTruthy();
  });

  it("says so when the Mac hasn't been in touch", async () => {
    vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    const quiet = { ...asked, last_seen_at: "2026-11-18T20:50:00+00:00" };
    render(<MacCheck mac={quiet} lastWorkout={null} />);
    const hhmm = new Date(quiet.last_seen_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    expect(screen.getByText(new RegExp(`hasn't been in touch since ${hhmm}`))).toBeTruthy();
  });

  it("says the Mac is checking once it picked the request up, however long the check takes", async () => {
    vi.useFakeTimers({ now: new Date("2026-11-18T21:10:00Z"), toFake: ["Date"] });
    render(<MacCheck mac={{ ...asked, last_seen_at: "2026-11-18T21:00:40+00:00" }} lastWorkout={null} />);
    expect(screen.getByText("Your Mac is checking…")).toBeTruthy();
    expect(screen.queryByText(/hasn't been in touch/)).toBeNull();
  });

  it("keeps waiting for a request still open when the page opens, and gives up polling after 20 minutes", async () => {
    vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    render(<MacCheck mac={asked} lastWorkout={null} />);
    expect(screen.getByText("Waiting for your Mac…")).toBeTruthy();
    server.mac = { ...asked, last_seen_at: "2026-11-18T21:00:40+00:00" }; // picked up, then busy for a long time
    await tick(10 * 60 * 1000);
    expect(screen.getByText("Your Mac is checking…")).toBeTruthy(); // a check can take ~15 minutes
    await tick(10 * 60 * 1000);
    const polls = server.calls.length;
    expect(polls).toBeGreaterThan(0);
    await tick(60000);
    expect(server.calls.length).toBe(polls);
    expect(screen.getByText(/Still waiting/)).toBeTruthy();
  });
});
