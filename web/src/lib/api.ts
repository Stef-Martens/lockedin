import { supabase } from "./supabase";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

export async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// One refresh at a time: parallel requests that all hit a 401 wait for the same new token.
let refreshing: Promise<string | null> | null = null;

/** A fresh access token, or null when the session can't be refreshed (signed out, refresh token gone). */
export function refreshToken(): Promise<string | null> {
  refreshing ??= supabase.auth.refreshSession()
    .then(({ data, error }) => (error ? null : data.session?.access_token ?? null))
    .catch(() => null)
    .finally(() => { refreshing = null; });
  return refreshing;
}

/** `/login`, with `?next=` so signing in again lands back where you were. */
export function loginPath(next: string): string {
  return next && next !== "/" && !next.startsWith("/login") ? `/login?next=${encodeURIComponent(next)}` : "/login";
}

type ExpiredHandler = (next: string) => void;
const reload: ExpiredHandler = (next) => window.location.assign(loginPath(next));
let onExpired: ExpiredHandler = reload;

/** App routes to the login page itself (no reload); until it registers, fall back to a page load. */
export function handleSessionExpired(fn: ExpiredHandler): () => void {
  onExpired = fn;
  return () => { onExpired = reload; };
}

let expired = false;

/** Sign out once, however many requests failed together, and go to the login page. */
async function sessionExpired(): Promise<void> {
  if (expired) return;
  expired = true;
  const next = window.location.pathname + window.location.search;
  await supabase.auth.signOut().catch(() => undefined);
  onExpired(next);
}

/**
 * fetch with the session token. A 401 first refreshes the token and retries once: an iPhone home-screen
 * app sleeps through supabase's refresh timer, so a stale token is normal there. Only when that fails too
 * does it sign out.
 */
export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = (auth: Record<string, string>) => fetch(path, { ...init, headers: { ...auth, ...(init.headers as Record<string, string> | undefined) } });
  const first = await authHeader();
  let res = await send(first);
  if (res.status === 401) {
    // Another request may have refreshed the token while this one was out: use that before refreshing again.
    const current = (await authHeader()).Authorization;
    const token = current && current !== first.Authorization ? current.slice("Bearer ".length) : await refreshToken();
    if (token) res = await send({ Authorization: `Bearer ${token}` });
    if (res.status === 401) {
      await sessionExpired();
      throw new ApiError(401, "Not signed in.");
    }
  }
  if (res.ok) expired = false;
  return res;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await authedFetch(path, { ...init, headers });
  if (!res.ok) throw await errorFrom(res);
  return (res.status === 204 ? null : await res.json()) as T;
}

/** An ApiError with the server's `detail` message when it sent one. */
export async function errorFrom(res: Response): Promise<ApiError> {
  let detail = `Something went wrong (${res.status}).`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, detail);
}

export function uploadFile<T>(path: string, file: File, fields: Record<string, string> = {}, signal?: AbortSignal): Promise<T> {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  fd.append("file", file);
  return apiFetch<T>(path, { method: "POST", body: fd, signal });
}

/**
 * Hand an authenticated file to the user. On iPhone (and other devices with a share sheet for files)
 * this opens the share sheet, where "Calendar" adds an .ics; elsewhere it downloads the file.
 */
export async function apiDownload(path: string, filename: string, type: string, signal?: AbortSignal): Promise<"shared" | "downloaded"> {
  const res = await authedFetch(path, { signal });
  if (!res.ok) throw new ApiError(res.status, `Download failed (${res.status}).`);
  const blob = await res.blob();
  const file = new File([blob], filename, { type });
  if (navigator.canShare?.({ files: [file] }) && /iPhone|iPad|Android/i.test(navigator.userAgent)) {
    await navigator.share({ files: [file], title: filename });
    return "shared";
  }
  const url = URL.createObjectURL(file);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return "downloaded";
}
