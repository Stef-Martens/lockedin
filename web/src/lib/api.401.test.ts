// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let token = "old";
const signOut = vi.fn(() => Promise.resolve({ error: null }));
const refreshSession = vi.fn(() => new Promise<{ data: { session: { access_token: string } | null }; error: Error | null }>((resolve) =>
  setTimeout(() => resolve(refreshWorks ? { data: { session: { access_token: (token = "new") } }, error: null }
    : { data: { session: null }, error: new Error("Refresh token not found") }), 5)));
let refreshWorks = true;
vi.mock("./supabase", () => ({
  supabase: { auth: { signOut, refreshSession, getSession: () => Promise.resolve({ data: { session: { access_token: token } } }) } },
}));

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
/** The server: only the "new" token is still valid. */
const server = vi.fn((_path: string, init?: RequestInit) => {
  const auth = (init?.headers as Record<string, string>).Authorization;
  return Promise.resolve(auth === "Bearer new" ? ok({ fine: true }) : new Response("{}", { status: 401 }));
});

beforeEach(() => {
  vi.resetModules();
  token = "old";
  refreshWorks = true;
  vi.stubGlobal("fetch", server);
});
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("a 401 from the API", () => {
  it("refreshes the token once for parallel requests and retries them", async () => {
    const { apiFetch } = await import("./api");
    const results = await Promise.all([apiFetch("/api/a"), apiFetch("/api/b"), apiFetch("/api/c")]);
    expect(results).toEqual([{ fine: true }, { fine: true }, { fine: true }]);
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(signOut).not.toHaveBeenCalled();
    expect(server).toHaveBeenCalledTimes(6);  // each request once with the old token, once with the new one
  });

  it("signs out once and goes to the login page, keeping where you were, when the refresh fails", async () => {
    refreshWorks = false;
    window.history.replaceState(null, "", "/trends/run?x=1");
    const { apiFetch, handleSessionExpired } = await import("./api");
    const expired = vi.fn();
    handleSessionExpired(expired);
    const all = await Promise.allSettled([apiFetch("/api/a"), apiFetch("/api/b")]);
    expect(all.every((r) => r.status === "rejected")).toBe(true);
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledTimes(1);
    expect(expired).toHaveBeenCalledWith("/trends/run?x=1");
  });

  it("uses a token another request already refreshed instead of refreshing again", async () => {
    const { apiFetch } = await import("./api");
    server.mockImplementationOnce(() => { token = "new"; return Promise.resolve(new Response("{}", { status: 401 })); });
    expect(await apiFetch("/api/a")).toEqual({ fine: true });
    expect(refreshSession).not.toHaveBeenCalled();
  });
});

describe("loginPath", () => {
  it("carries the page you were on, but not home or the login page itself", async () => {
    const { loginPath } = await import("./api");
    expect(loginPath("/trends/run?x=1")).toBe("/login?next=%2Ftrends%2Frun%3Fx%3D1");
    expect(loginPath("/")).toBe("/login");
    expect(loginPath("/login?next=%2Fbody")).toBe("/login");
  });
});
