import { describe, expect, it } from "vitest";

import { consumeSseStream, parseSseBlock, type ParsedSseEvent } from "@/app/lib/sse";

describe("parseSseBlock", () => {
  it("parses CRLF blocks into events", () => {
    const block = [
      "event: on_node_start\r",
      'data: {"node":"planner","state":"active"}\r',
      "",
    ].join("\n");

    const parsed = parseSseBlock(block);
    expect(parsed).toEqual({
      event: "on_node_start",
      data: { node: "planner", state: "active" },
    });
  });

  it("returns an error event when data JSON is malformed", () => {
    const parsed = parseSseBlock("event: on_debug_event\ndata: {broken}");
    expect(parsed).toEqual({
      event: "error",
      data: {
        message: "Failed to parse SSE payload.",
        raw: "{broken}",
      },
    });
  });
});

describe("consumeSseStream", () => {
  it("consumes chunked SSE payloads and emits parsed events", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode('event: run_started\r\ndata: {"event_id":1}\r\n\r\n')
        );
        controller.enqueue(
          encoder.encode('event: run_complete\ndata: {"event_id":2}\n\n')
        );
        controller.close();
      },
    });

    const response = new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });

    const events: ParsedSseEvent[] = [];
    await consumeSseStream(response, (event) => events.push(event));

    expect(events).toEqual([
      { event: "run_started", data: { event_id: 1 } },
      { event: "run_complete", data: { event_id: 2 } },
    ]);
  });
});
