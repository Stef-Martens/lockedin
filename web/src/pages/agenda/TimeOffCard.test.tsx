// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TimeOffEntry } from "../../lib/timeoff";
import TimeOffCard from "./TimeOffCard";

const OPERATION: TimeOffEntry = {
  id: 7, reason: "injury", label: "Operation", start: "2026-12-03", end: "2027-01-02",
  restrictions: [{ category: "run", until: "2026-12-17" }, { category: "upper", until: "2027-01-02" }],
};
const VACATION: TimeOffEntry = {
  id: 8, reason: "vacation", label: null, start: "2027-02-10", end: "2027-02-17", restrictions: [{ category: "all", until: "2027-02-17" }],
};

let entries: TimeOffEntry[] = [];
let failWith: Error | null = null;
const apiFetch = vi.fn((_path: string, init?: RequestInit): Promise<unknown> => {
  if (init?.method && failWith) return Promise.reject(failWith);
  if (init?.method === "POST") return Promise.resolve({ id: 9, ...JSON.parse(init.body as string), end: "x" });
  if (init?.method === "PATCH" || init?.method === "DELETE") return Promise.resolve(null);
  return Promise.resolve(entries);
});
vi.mock("../../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => apiFetch(path, init),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));

beforeEach(() => { entries = [OPERATION, VACATION]; failWith = null; });
afterEach(() => { cleanup(); apiFetch.mockClear(); });

const sent = (method: string) => {
  const call = apiFetch.mock.calls.find((c) => c[1]?.method === method)!;
  return { path: call[0], body: call[1]?.body ? JSON.parse(call[1].body as string) : null };
};

describe("TimeOffCard", () => {
  it("lists current and upcoming time off, one line each", async () => {
    render(<TimeOffCard onChange={() => undefined} />);
    expect(await screen.findByText("Operation · from 3 Dec · no running until 17 Dec, no upper body until 2 Jan")).toBeTruthy();
    expect(screen.getByText("Vacation · from 10 Feb · everything off until 17 Feb")).toBeTruthy();
  });

  it("says so when nothing is planned", async () => {
    entries = [];
    render(<TimeOffCard onChange={() => undefined} />);
    expect(await screen.findByText(/No time off planned/)).toBeTruthy();
  });

  it("adds a vacation with the 'everything off' shortcut", async () => {
    const changed = vi.fn();
    render(<TimeOffCard onChange={changed} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add time off" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "vacation" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-12-20" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2027-01-03" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    const { path, body } = sent("POST");
    expect(path).toBe("/api/time-off");
    expect(body).toEqual({ reason: "vacation", label: null, start: "2026-12-20", restrictions: [{ category: "all", until: "2027-01-03" }] });
  });

  it("adds an operation with a date per activity", async () => {
    render(<TimeOffCard onChange={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add time off" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "injury" } });
    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "Knee" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-12-03" } });
    fireEvent.change(screen.getByLabelText("Running"), { target: { value: "off" } });
    fireEvent.change(screen.getByLabelText("Running until"), { target: { value: "2026-12-17" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent("POST").body).toEqual({ reason: "injury", label: "Knee", start: "2026-12-03",
      restrictions: [{ category: "run", until: "2026-12-17" }] }));
  });

  it("asks for something to be off before saving", async () => {
    render(<TimeOffCard onChange={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add time off" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "injury" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Pick at least one thing that's off.");
    expect(apiFetch.mock.calls.some((c) => c[1]?.method)).toBe(false);
  });

  it("edits an entry with a PATCH", async () => {
    const changed = vi.fn();
    render(<TimeOffCard onChange={changed} />);
    const row = (await screen.findByText(/^Operation · from 3 Dec/)).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));
    expect((screen.getByLabelText("Running until") as HTMLInputElement).value).toBe("2026-12-17");
    fireEvent.change(screen.getByLabelText("Running until"), { target: { value: "2026-12-24" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    const { path, body } = sent("PATCH");
    expect(path).toBe("/api/time-off/7");
    expect(body).toEqual({ reason: "injury", label: "Operation", start: "2026-12-03",
      restrictions: [{ category: "run", until: "2026-12-24" }, { category: "upper", until: "2027-01-02" }] });
  });

  it("deletes only after a confirm", async () => {
    const changed = vi.fn();
    render(<TimeOffCard onChange={changed} />);
    const row = (await screen.findByText(/^Operation · from 3 Dec/)).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    expect(apiFetch.mock.calls.some((c) => c[1]?.method === "DELETE")).toBe(false);
    fireEvent.click(within(row).getByRole("button", { name: "Yes, delete it" }));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(sent("DELETE").path).toBe("/api/time-off/7");
  });

  it("keeps a vacation's 'everything off' in sight after switching to an injury", async () => {
    render(<TimeOffCard onChange={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add time off" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "vacation" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-12-03" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-12-05" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "injury" } });
    expect(screen.getByLabelText<HTMLSelectElement>("Everything").value).toBe("off");
    expect(screen.getByLabelText<HTMLInputElement>("Everything until").value).toBe("2026-12-05");
    fireEvent.change(screen.getByLabelText("Everything"), { target: { value: "fine" } });
    fireEvent.change(screen.getByLabelText("Running"), { target: { value: "off" } });
    fireEvent.change(screen.getByLabelText("Running until"), { target: { value: "2026-12-17" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent("POST").body.restrictions).toEqual([{ category: "run", until: "2026-12-17" }]));
  });

  it("shows and can remove 'everything off' on an injury", async () => {
    entries = [{ ...OPERATION, restrictions: [...OPERATION.restrictions, { category: "all", until: "2026-12-05" }] }];
    render(<TimeOffCard onChange={() => undefined} />);
    const row = (await screen.findByText(/^Operation · from 3 Dec/)).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText<HTMLInputElement>("Everything until").value).toBe("2026-12-05");
    fireEvent.change(screen.getByLabelText("Everything"), { target: { value: "fine" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent("PATCH").body.restrictions).toEqual(OPERATION.restrictions));
  });

  it("can't pick an end before the start", async () => {
    render(<TimeOffCard onChange={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add time off" }));
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-12-03" } });
    expect(screen.getByLabelText<HTMLInputElement>("To").min).toBe("2026-12-03");
    fireEvent.change(screen.getByLabelText("Running"), { target: { value: "off" } });
    expect(screen.getByLabelText<HTMLInputElement>("Running until").min).toBe("2026-12-03");
  });

  it("clears an earlier error once something works", async () => {
    failWith = new Error("Network down");
    render(<TimeOffCard onChange={() => undefined} />);
    const row = (await screen.findByText(/^Operation · from 3 Dec/)).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(row).getByRole("button", { name: "Yes, delete it" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Network down");
    failWith = null;
    fireEvent.click(within(row).getByRole("button", { name: "Delete" }));
    fireEvent.click(within(row).getByRole("button", { name: "Yes, delete it" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("shows the server's message when it refuses", async () => {
    failWith = new Error("Every restriction must end on or after the start.");
    render(<TimeOffCard onChange={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add time off" }));
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-12-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Every restriction must end on or after the start.");
  });
});
