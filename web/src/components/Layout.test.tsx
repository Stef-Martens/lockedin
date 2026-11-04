// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Layout from "./Layout";

const status = vi.hoisted(() => ({ zwift: { last_import_at: null as string | null }, healthfit: { last_import_at: null as string | null } }));
vi.mock("../lib/api", () => ({ apiFetch: () => Promise.resolve(status) }));
vi.mock("../lib/supabase", () => ({ supabase: { auth: { signOut: vi.fn() } } }));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  status.zwift.last_import_at = null;
  status.healthfit.last_import_at = null;
});

describe("Layout", () => {
  it("dates the Mac sync by its newest upload, a Watch workout as much as a Zwift ride", async () => {
    vi.useFakeTimers({ now: new Date("2026-11-04T21:00:00Z"), toFake: ["Date"] });
    status.zwift.last_import_at = "2026-10-29T12:00:00+00:00";
    status.healthfit.last_import_at = "2026-11-04T18:00:00+00:00";
    render(<MemoryRouter><Routes><Route element={<Layout />}><Route index element={<p>home</p>} /></Route></Routes></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText(/Mac sync · 3 h ago/).length).toBeGreaterThan(0));
  });

  it("puts Agenda second and tucks Trends, Forecast, Body, Import and Sign out under More on phones", () => {
    render(<MemoryRouter><Routes><Route element={<Layout />}><Route index element={<p>home</p>} /></Route></Routes></MemoryRouter>);
    const side = screen.getAllByRole("navigation", { name: "Main" })[0];
    expect([...side.querySelectorAll("a")].map((a) => a.textContent).slice(0, 2)).toEqual(["Overview", "Agenda"]);
    const tabs = screen.getByRole("navigation", { name: "Tabs" });
    expect([...tabs.querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Home", "Agenda", "Coach", "Activities", "Muscles"]);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Trends", "Forecast", "Body", "Import", "Sign out"]);
  });

  it("gives focus back to More on Escape", () => {
    render(<MemoryRouter><Routes><Route element={<Layout />}><Route index element={<p>home</p>} /></Route></Routes></MemoryRouter>);
    const more = screen.getByRole("button", { name: "More" });
    fireEvent.click(more);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(more);
  });

  it("asks before signing out, and isn't next to the logo on phones", async () => {
    const { supabase } = await import("../lib/supabase");
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<MemoryRouter><Routes><Route element={<Layout />}><Route index element={<p>home</p>} /></Route></Routes></MemoryRouter>);
    expect(document.querySelector(".topbar button")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(supabase.auth.signOut).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(supabase.auth.signOut).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenCalledWith("Sign out of LockedIn?");
    confirm.mockRestore();
  });

  it("closes More when you pick the page you're already on", () => {
    render(<MemoryRouter initialEntries={["/body"]}><Routes><Route element={<Layout />}><Route path="body" element={<p>body</p>} /></Route></Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Body" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
