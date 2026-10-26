import { ApiError, authHeader, errorFrom } from "./api";

/** Split a chunk of a server-sent-event stream into JSON `data:` events, carrying any unfinished event over. */
export function parseSSE(chunk: string, carry: string): { events: unknown[]; carry: string } {
  const parts = (carry + chunk).replace(/\r\n/g, "\n").split("\n\n");
  const rest = parts.pop() ?? "";
  const events = parts.flatMap((part) =>
    part.split("\n").filter((line) => line.startsWith("data:")).map((line) => JSON.parse(line.slice(5).trim())));
  return { events, carry: rest };
}

/** POST JSON and hand each streamed event to `onEvent` until the server closes the stream. */
export async function postStream(path: string, body: unknown, onEvent: (event: unknown) => void, signal?: AbortSignal) {
  const res = await fetch(path, {
    method: "POST", signal, body: JSON.stringify(body),
    headers: { ...(await authHeader()), "Content-Type": "application/json" },
  });
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) throw new ApiError(0, "No response stream.");
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let carry = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSSE(value, carry);
    carry = parsed.carry;
    parsed.events.forEach(onEvent);
  }
}
