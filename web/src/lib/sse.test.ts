import { describe, expect, it, vi } from "vitest";
import { parseSSE } from "./sse";

vi.mock("./supabase", () => ({ supabase: {} }));  // no Supabase project needed to parse a stream

describe("parseSSE", () => {
  it("parses complete events and keeps the unfinished tail", () => {
    const { events, carry } = parseSSE('data: {"type":"text","text":"Hi"}\n\ndata: {"type":"do', "");
    expect(events).toEqual([{ type: "text", text: "Hi" }]);
    expect(parseSSE('ne"}\n\n', carry).events).toEqual([{ type: "done" }]);
  });

  it("handles several events in one chunk and CRLF line endings", () => {
    const { events, carry } = parseSSE('data: {"a":1}\r\n\r\ndata: {"b":2}\n\n', "");
    expect(events).toEqual([{ a: 1 }, { b: 2 }]);
    expect(carry).toBe("");
  });

  it("ignores comments and lines that are not data", () => {
    expect(parseSSE(': keep-alive\n\nevent: x\ndata: {"c":3}\n\n', "").events).toEqual([{ c: 3 }]);
  });
});
