// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import Agenda from "./Agenda";

// Real router hooks (no mocks): the page must survive going from "loading" to the loaded week.
vi.mock("../lib/api", () => ({
  apiFetch: (path: string) => Promise.resolve(path === "/api/time-off" ? [] : { week_start: "2026-10-26", today: "2026-10-26", items: [], time_off: [] }),
  ApiError: class ApiError extends Error {},
}));
afterEach(cleanup);

it("renders the loaded week with the real router", async () => {
  render(<MemoryRouter initialEntries={["/agenda"]}><Agenda /></MemoryRouter>);
  expect(await screen.findByText(/Nothing planned this week/)).toBeTruthy();
});
