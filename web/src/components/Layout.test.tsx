// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Layout from "./Layout";

vi.mock("../lib/api", () => ({ apiFetch: () => Promise.resolve({ zwift: { last_import_at: null } }) }));
vi.mock("../lib/supabase", () => ({ supabase: { auth: { signOut: vi.fn() } } }));
afterEach(cleanup);

describe("Layout", () => {
  it("puts Agenda second and tucks Trends, Body and Import under More on phones", () => {
    render(<MemoryRouter><Routes><Route element={<Layout />}><Route index element={<p>home</p>} /></Route></Routes></MemoryRouter>);
    const side = screen.getAllByRole("navigation", { name: "Main" })[0];
    expect([...side.querySelectorAll("a")].map((a) => a.textContent).slice(0, 2)).toEqual(["Overview", "Agenda"]);
    const tabs = screen.getByRole("navigation", { name: "Tabs" });
    expect([...tabs.querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Home", "Agenda", "Coach", "Activities", "Muscles"]);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Trends", "Body", "Import"]);
  });
});
