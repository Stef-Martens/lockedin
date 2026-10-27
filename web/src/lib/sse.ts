import { ApiError, authedFetch, errorFrom } from "./api";

/** Split a chunk of a server-sent-event stream into JSON `data:` events, carrying any unfinished event over. */
export function parseSSE(chunk: string, carry: string): { events: unknown[]; carry: string } {
  const parts = (carry + chunk).replace(/\r\n/g, "\n").split("\n\n");
  const rest = parts.pop() ?? "";
  const events = parts.flatMap((part) =>
    part.split("\n").filter((line) => line.startsWith("data:")).map((line) => JSON.parse(line.slice(5).trim())));
  return { events, carry: rest };
}

/**
 * POST JSON and hand each streamed event to `onEvent` until the server closes the stream.
 * Aborting `signal` stops reading; the promise then rejects with an AbortError.
 */
export async function postStream(path: string, body: unknown, onEvent: (event: unknown) => void, signal?: AbortSignal) {
  // Same session handling as apiFetch: a 401 refreshes the token and retries once before signing out.
  const res = await authedFetch(path, {
    method: "POST", signal, body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) throw new ApiError(0, "No response stream.");
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const stop = () => { reader.cancel().catch(() => undefined); };
  signal?.addEventListener("abort", stop, { once: true });
  try {
    let carry = "";
    for (;;) {
      const { value, done } = await reader.read();
      signal?.throwIfAborted();
      if (done) break;
      const parsed = parseSSE(value, carry);
      carry = parsed.carry;
      parsed.events.forEach(onEvent);
    }
  } finally {
    signal?.removeEventListener("abort", stop);
  }
}
