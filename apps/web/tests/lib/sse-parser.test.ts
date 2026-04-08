import { describe, expect, it } from "vitest";

import { parseSSEStream } from "../../lib/chat/sse";

describe("parseSSEStream", () => {
  it("parses multiple event frames from chunked stream", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            "id: 1\nevent: reasoning\ndata: {\"text\":\"step-1\"}\n\n" +
              "id: 2\nevent: tool\ndata: {\"status\":\"ok\"}"
          )
        );
        controller.enqueue(encoder.encode("\n\n"));
        controller.close();
      }
    });

    const events = [];
    for await (const event of parseSSEStream(stream)) {
      events.push(event);
    }

    expect(events).toEqual([
      { id: "1", event: "reasoning", data: { text: "step-1" } },
      { id: "2", event: "tool", data: { status: "ok" } }
    ]);
  });

  it("ignores empty/comment frames and falls back to raw text for non-json data", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            ":keepalive\n\n" +
              "event: final\n" +
              "data: plain\n" +
              "data: text\n\n" +
              "event: noop\n\n"
          )
        );
        controller.close();
      }
    });

    const events = [];
    for await (const event of parseSSEStream(stream)) {
      events.push(event);
    }

    expect(events).toEqual([{ id: undefined, event: "final", data: "plain\ntext" }]);
  });
});
