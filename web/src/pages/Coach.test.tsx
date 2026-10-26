// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Coach from "./Coach";

let ready = true;
vi.mock("../lib/api", () => ({
  apiFetch: (path: string, init?: RequestInit) => Promise.resolve(
    init?.method === "POST" ? { id: 1 }
      : path === "/api/coach/status" ? { ready, model: "claude-opus-5-5" }
      : path === "/api/coach/conversations" ? [] : path.startsWith("/api/coach/goals") ? [] : { id: 1 }),
  ApiError: class ApiError extends Error { status = 0; detail = ""; },
}));
vi.mock("../lib/sse", () => ({
  postStream: (_p: string, _b: unknown, onEvent: (e: unknown) => void) => {
    [{ type: "text", text: "half a sen" }, { type: "reset" }, { type: "text", text: "Whole answer." }, { type: "done" }].forEach(onEvent);
    return Promise.resolve();
  },
}));
afterEach(cleanup);
const open = () => render(<MemoryRouter initialEntries={["/coach"]}><Routes><Route path="/coach" element={<Coach />} /><Route path="/coach/:id" element={<Coach />} /></Routes></MemoryRouter>);

describe("Coach page", () => {
  it("says it isn't set up before you type anything", async () => {
    ready = false;
    open();
    expect(await screen.findByText(/The coach isn't set up yet/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("drops partial text when the answer restarts", async () => {
    ready = true;
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Help me set goals" }));
    await waitFor(() => expect(screen.getByText("Whole answer.")).toBeTruthy());
    expect(screen.queryByText(/half a sen/)).toBeNull();
  });
});
