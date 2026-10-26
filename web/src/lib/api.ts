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

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = { ...(await authHeader()), ...(init.headers as Record<string, string> | undefined) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    await supabase.auth.signOut();
    window.location.assign("/login");
    throw new ApiError(401, "Not signed in.");
  }
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

export function uploadFile<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  fd.append("file", file);
  return apiFetch<T>(path, { method: "POST", body: fd });
}

/**
 * Hand an authenticated file to the user. On iPhone (and other devices with a share sheet for files)
 * this opens the share sheet, where "Calendar" adds an .ics; elsewhere it downloads the file.
 */
export async function apiDownload(path: string, filename: string, type: string): Promise<"shared" | "downloaded"> {
  const res = await fetch(path, { headers: await authHeader() });
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
