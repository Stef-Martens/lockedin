// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";

const signOut = vi.fn(() => Promise.resolve());
const refreshSession = vi.fn(() => Promise.resolve({ data: { session: null }, error: new Error("Auth session missing!") }));
vi.mock("./supabase", () => ({
  supabase: { auth: { signOut, refreshSession, getSession: () => Promise.resolve({ data: { session: null } }) } },
}));
afterEach(() => vi.unstubAllGlobals());

it("tries a refresh, then signs out and goes to the login page when the session expired mid-chat", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, pathname: "/coach/3", search: "", assign });
  const { postStream } = await import("./sse");
  await expect(postStream("/api/coach/conversations/3/messages", { text: "hi" }, () => undefined)).rejects.toThrow();
  expect(refreshSession).toHaveBeenCalledTimes(1);
  expect(signOut).toHaveBeenCalled();
  expect(assign).toHaveBeenCalledWith("/login?next=%2Fcoach%2F3");
});
