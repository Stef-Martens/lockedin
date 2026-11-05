// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import VerdictCard from "./VerdictCard";

const ACTIVITY = { id: 1, sport: "run", day: "2026-11-04", start_at: "2026-11-04T07:00:00+01:00", title: "Tempo", item_id: 7 };
const reply = (verdict: object, activity: object | null = ACTIVITY) => ({ activity, verdict });
const DONE = { status: "done", label: "close", text: "Three of four blocks were inside the range." };

const apiFetch = vi.fn((_path: string) => Promise.resolve<unknown>(reply(DONE)));
vi.mock("../lib/api", () => ({ apiFetch: (path: string) => apiFetch(path) }));

const flush = () => act(async () => { await Promise.resolve(); });
const mount = async (el: React.ReactElement) => { render(<MemoryRouter>{el}</MemoryRouter>); await flush(); };

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); apiFetch.mockReset(); apiFetch.mockImplementation(() => Promise.resolve(reply(DONE))); });

describe("VerdictCard", () => {
  it("shows the header, label, text and a link to the session when there is an item", async () => {
    await mount(<VerdictCard source="latest" />);
    expect(apiFetch).toHaveBeenCalledWith("/api/verdicts/latest");
    expect(screen.getByText("Last workout")).toBeTruthy();
    expect(screen.getByText(/Tempo/)).toBeTruthy();
    expect(screen.getByText("Close to plan")).toBeTruthy();
    expect(screen.getByText("Three of four blocks were inside the range.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See how it went" }).getAttribute("href")).toBe("/agenda/7");
  });

  it("links to the activity when nothing was planned", async () => {
    apiFetch.mockResolvedValue(reply({ status: "done", label: "unplanned", text: "A steady run." }, { ...ACTIVITY, item_id: null, title: null }));
    await mount(<VerdictCard source="latest" />);
    expect(screen.getByText("Not planned")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See how it went" }).getAttribute("href")).toBe("/activities/1");
  });

  it.each([["on_plan", "On plan"], ["off_plan", "Off plan"]])("labels %s as %s", async (label, shown) => {
    apiFetch.mockResolvedValue(reply({ status: "done", label, text: "x" }));
    await mount(<VerdictCard source="latest" />);
    expect(screen.getByText(shown)).toBeTruthy();
  });

  it.each([
    ["over_budget", "Today's coach budget is used up; this appears tomorrow."],
    ["failed", "Couldn't write this one; it tries again next time you open this page."],
  ])("says so when %s, under the header", async (status, copy) => {
    apiFetch.mockResolvedValue(reply({ status }));
    await mount(<VerdictCard source="latest" />);
    expect(screen.getByText("Last workout")).toBeTruthy();
    expect(screen.getByText(copy)).toBeTruthy();
  });

  it("checks again every 3 seconds while writing, then shows the result", async () => {
    apiFetch.mockResolvedValueOnce(reply({ status: "writing" }));
    await mount(<VerdictCard source="latest" />);
    expect(screen.getByText("The coach is looking at it…")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(2900); });
    expect(apiFetch).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Close to plan")).toBeTruthy();
    expect(screen.queryByText("The coach is looking at it…")).toBeNull();
  });

  it("stops after 90 seconds and keeps the being-written text", async () => {
    apiFetch.mockResolvedValue(reply({ status: "writing" }));
    await mount(<VerdictCard source="latest" />);
    await act(async () => { await vi.advanceTimersByTimeAsync(200_000); });
    expect(apiFetch).toHaveBeenCalledTimes(31); // the first look and one every 3 s for 90 s
    expect(screen.getByText("The coach is looking at it…")).toBeTruthy();
  });

  it("stops polling on unmount", async () => {
    apiFetch.mockResolvedValue(reply({ status: "writing" }));
    await mount(<VerdictCard source="latest" />);
    cleanup();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("ignores a response that arrives after unmount", async () => {
    let resolve!: (v: unknown) => void;
    apiFetch.mockReturnValue(new Promise((r) => { resolve = r; }));
    await mount(<VerdictCard source="latest" />);
    cleanup();
    resolve(reply({ status: "writing" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["no workout", reply({ status: "none" }, null)],
    ["none", reply({ status: "none" })],
    ["a null activity", reply({ status: "done", label: "close", text: "x" }, null)],
  ])("renders nothing for %s", async (_n, r) => {
    apiFetch.mockResolvedValue(r);
    await mount(<VerdictCard source="latest" />);
    expect(screen.queryByText("Last workout")).toBeNull();
    expect(document.body.textContent).toBe("");
  });

  it("renders nothing when the fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("500"));
    await mount(<VerdictCard source="latest" />);
    expect(document.body.textContent).toBe("");
  });

  it("leaves out the header and link on a page that already names the workout", async () => {
    await mount(<VerdictCard activityId={1} />);
    expect(apiFetch).toHaveBeenCalledWith("/api/verdicts/1");
    expect(screen.getByText("Close to plan")).toBeTruthy();
    expect(screen.queryByText("Last workout")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
