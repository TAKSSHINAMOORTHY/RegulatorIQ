import { describe, it, expect } from "vitest";
import { parseSSEStream } from "@/lib/sse";
import type { AgentEvent } from "@/lib/generated/events";

function createStreamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe("SSE Stream Parser", () => {
  it("parses normal events with CRLF and LF", async () => {
    const raw = "event: status\r\ndata: {\"seq\": 1, \"step\": \"retrieval\"}\r\n\r\nevent: token\ndata: {\"seq\": 2, \"delta\": \"Hello\"}\n\n";
    const stream = createStreamFromChunks([raw]);
    const received: AgentEvent[] = [];

    await parseSSEStream(stream, {
      onEvent: (ev) => received.push(ev),
    });

    expect(received.length).toBe(2);
    expect(received[0].type).toBe("status");
    expect(received[0].step).toBe("retrieval");
    expect(received[1].type).toBe("token");
    expect((received[1] as any).delta).toBe("Hello");
  });

  it("handles events split at arbitrary byte boundaries", async () => {
    const fullPayload = 'event: token\ndata: {"seq": 3, "step": "generation", "delta": "world"}\n\n';
    // Split into 3-byte chunks
    const chunks: string[] = [];
    for (let i = 0; i < fullPayload.length; i += 3) {
      chunks.push(fullPayload.slice(i, i + 3));
    }

    const stream = createStreamFromChunks(chunks);
    const received: AgentEvent[] = [];

    await parseSSEStream(stream, {
      onEvent: (ev) => received.push(ev),
    });

    expect(received.length).toBe(1);
    expect(received[0].type).toBe("token");
    expect((received[0] as any).delta).toBe("world");
  });

  it("handles comments and heartbeats gracefully", async () => {
    const raw = ": ping\n\nevent: done\ndata: {\"seq\": 4, \"step\": \"done\"}\n\n: heartbeat\n\n";
    const stream = createStreamFromChunks([raw]);
    const received: AgentEvent[] = [];
    const comments: string[] = [];

    await parseSSEStream(stream, {
      onEvent: (ev) => received.push(ev),
      onComment: (c) => comments.push(c),
    });

    expect(received.length).toBe(1);
    expect(comments).toContain("ping");
    expect(comments).toContain("heartbeat");
  });

  it("handles unknown fields and malformed JSON without crashing", async () => {
    const raw = "foo: bar\ndata: { malformed json\n\nevent: status\ndata: {\"seq\": 5, \"step\": \"ok\"}\n\n";
    const stream = createStreamFromChunks([raw]);
    const received: AgentEvent[] = [];
    const errors: Error[] = [];

    const { unknownEventsCount } = await parseSSEStream(stream, {
      onEvent: (ev) => received.push(ev),
      onError: (err) => errors.push(err),
    });

    expect(received.length).toBe(1);
    expect(received[0].step).toBe("ok");
    expect(errors.length).toBe(1);
    expect(unknownEventsCount).toBeGreaterThan(0);
  });
});
