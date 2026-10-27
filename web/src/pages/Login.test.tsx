// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AfterLogin, nextPath } from "./Login";

vi.mock("../lib/supabase", () => ({ supabase: { auth: {} } }));
afterEach(cleanup);

describe("after signing in", () => {
  it("goes back to the page you were on", () => {
    render(
      <MemoryRouter initialEntries={["/login?next=%2Ftrends%2Frun"]}>
        <Routes><Route path="login" element={<AfterLogin />} /><Route path="trends/run" element={<p>run trends</p>} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("run trends")).toBeTruthy();
  });

  it("only follows paths inside the app", () => {
    expect(nextPath("?next=%2Fbody")).toBe("/body");
    expect(nextPath("?next=https%3A%2F%2Fevil.example")).toBe("/");
    expect(nextPath("?next=%2F%2Fevil.example")).toBe("/");
    expect(nextPath("?next=%2F%5Cevil.example")).toBe("/");  // browsers read /\ as //
    expect(nextPath("?next=%2F%09%2Fevil.example")).toBe("/");
    expect(nextPath("")).toBe("/");
  });
});
