// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Import from "./Import";

const uploadFile = vi.fn((path: string, _file?: File): Promise<unknown> => Promise.resolve(path.includes("hevy")
  ? { new: 1, updated: 0, unchanged: 0, skipped: [] } : { status: "imported", sha256: "x", activity_id: 9, error: null }));
vi.mock("../lib/api", () => ({
  apiFetch: () => Promise.resolve({ zwift: { last_import_at: null, count: 0 }, healthfit: { last_import_at: null, count: 0 },
    hevy: { last_import_at: null, count: 0 }, last_tape_measurement_on: null }),
  uploadFile: (path: string, file: File) => uploadFile(path, file),
}));
afterEach(() => { cleanup(); uploadFile.mockClear(); });

const pick = (input: HTMLInputElement, file: File) => {
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  fireEvent.change(input);
};

describe("Import pickers", () => {
  it("uploads the same Hevy file again when you pick it a second time", async () => {
    render(<MemoryRouter><Import /></MemoryRouter>);
    const input = screen.getByTestId("hevy-input") as HTMLInputElement;
    const csv = new File(["a,b"], "workouts.csv", { type: "text/csv" });
    pick(input, csv);
    await screen.findByText("1 new");
    expect(input.value).toBe("");
    pick(input, csv);
    await waitFor(() => expect(uploadFile).toHaveBeenCalledTimes(2));
  });

  it("opens the Hevy picker from a real, focusable button", () => {
    render(<MemoryRouter><Import /></MemoryRouter>);
    const input = screen.getByTestId("hevy-input") as HTMLInputElement;
    const click = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: "Choose CSV" }));
    expect(click).toHaveBeenCalled();
  });

  it("opens the .fit picker with Space as well as Enter", () => {
    render(<MemoryRouter><Import /></MemoryRouter>);
    const click = vi.spyOn(screen.getByTestId("fit-input") as HTMLInputElement, "click");
    const zone = screen.getByRole("button", { name: /Drop .fit files here/ });
    fireEvent.keyDown(zone, { key: " " });
    fireEvent.keyDown(zone, { key: "Enter" });
    expect(click).toHaveBeenCalledTimes(2);
  });
});
