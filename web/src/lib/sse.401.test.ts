// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";

const signOut = vi.fn(() => Promise.resolve());
vi.mock("./supabase", () => ({ supabase: { auth: { signOut, getSession: () => Promise.resolve({ data: { session: null } }) } } }));
afterEach(() => vi.unstubAllGlobals());

it("signs out and goes to the login page when the session expired mid-chat", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  const { postStream } = await import("./sse");
  await expect(postStream("/api/coach/conversations/1/messages", { text: "hi" }, () => undefined)).rejects.toThrow();
  expect(signOut).toHaveBeenCalled();
  expect(assign).toHaveBeenCalledWith("/login");
});
