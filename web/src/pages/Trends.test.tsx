// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import Trends from "./Trends";

const replies: Record<string, () => Promise<unknown>> = {};
vi.mock("../lib/api", () => {
  class ApiError extends Error { constructor(public status: number, public detail: string) { super(detail); } }
  return {
    ApiError,
    apiFetch: (path: string) => (Object.entries(replies).find(([p]) => path.startsWith(p))?.[1] ?? (() => Promise.resolve({})))(),
  };
});
beforeAll(() => {
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined })) as never;
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as never;
});
afterEach(() => { cleanup(); Object.keys(replies).forEach((k) => delete replies[k]); });

const NO_RIDES = { rides: [], ftp: null, mix: { sport: "bike", counts: { easy: 0, steady: 0, long: 0, hard: 0 }, unclassified: 0 } };
const days = Array.from({ length: 180 }, (_, n) => {
  const day = new Date(Date.UTC(2026, 4, 1 + n)).toISOString().slice(0, 10);
  return { day, load: n % 3 ? 40 : 0, fitness: 30 + n / 20, fatigue: 35 + (n % 7), form: -5 - (n % 7) };
});
const open = () => render(<MemoryRouter initialEntries={["/trends/bike"]}><Routes><Route path="/trends/:sport" element={<Trends />} /></Routes></MemoryRouter>);

describe("Trends", () => {
  it("shows today's fitness, fatigue and form in words above the sport", async () => {
    replies["/api/load"] = () => Promise.resolve({ days, today: { fitness: 38.1, fatigue: 52.0, form: -13.9 } });
    replies["/api/trends/bike"] = () => Promise.resolve(NO_RIDES);
    open();
    expect(await screen.findByRole("heading", { name: "Training load" })).toBeTruthy();
    expect(screen.getByText("38")).toBeTruthy();
    expect(screen.getByText("52")).toBeTruthy();
    expect(screen.getByText("−14")).toBeTruthy();
    expect(screen.getByText("Building")).toBeTruthy();
    expect(screen.getByText("your 6-week average load")).toBeTruthy();
    expect(await screen.findByText("No rides yet")).toBeTruthy();
  });

  it("says when there's nothing to go on yet", async () => {
    replies["/api/load"] = () => Promise.resolve({ days: [], today: null });
    replies["/api/trends/bike"] = () => Promise.resolve(NO_RIDES);
    open();
    expect(await screen.findByText(/show up here once you've trained/)).toBeTruthy();
  });

  it("leaves the card out while the server doesn't have the endpoint, and the rest of Trends still works", async () => {
    replies["/api/load"] = () => Promise.reject(new ApiError(404, "Not Found"));
    replies["/api/trends/bike"] = () => Promise.resolve(NO_RIDES);
    open();
    expect(await screen.findByText("No rides yet")).toBeTruthy();
    expect(screen.queryByText("Training load")).toBeNull();
    expect(screen.queryByText(/isn't available/)).toBeNull();
  });

  it("keeps a failed load request quiet, and offers a retry when the sport itself fails", async () => {
    replies["/api/load"] = () => Promise.reject(new ApiError(500, "boom"));
    replies["/api/trends/bike"] = () => Promise.reject(new Error("offline"));
    open();
    expect(await screen.findByText("Training load isn't available right now.")).toBeTruthy();
    expect(await screen.findByText(/Couldn't load this right now/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
