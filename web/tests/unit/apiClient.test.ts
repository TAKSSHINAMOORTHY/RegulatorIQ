import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiClient, ApiError } from "@/lib/apiClient";

describe("ApiClient", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("probes health with cache", async () => {
    let fetchCount = 0;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      fetchCount++;
      return new Response(JSON.stringify({ status: "alive" }), { status: 200 });
    });

    const client = new ApiClient(["http://host1:8000"]);
    const h1 = await client.checkHealth("http://host1:8000");
    const h2 = await client.checkHealth("http://host1:8000");

    expect(h1).toBe(true);
    expect(h2).toBe(true);
    // Cached for 60 seconds
    expect(fetchCount).toBe(1);
  });

  it("fails over to secondary host on initial 5xx error", async () => {
    let callIndex = 0;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      callIndex++;
      if (url.includes("host1")) {
        return new Response("Internal Server Error", { status: 500 });
      }
      // host2 succeeds
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            new TextEncoder().encode(
              'event: token\ndata: {"delta": "Success from host2"}\n\n'
            )
          );
          controller.close();
        },
      });
      return new Response(stream, { status: 200 });
    });

    const client = new ApiClient(["http://host1:8000", "http://host2:8000"]);
    const stream = client.ask({ question: "Test failover" });
    const events: any[] = [];
    for await (const ev of stream) {
      events.push(ev);
    }

    expect(events.length).toBe(1);
    expect(events[0].delta).toBe("Success from host2");
    expect(callIndex).toBe(2);
  });

  it("throws typed ApiError for 429 rate limit", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response("Too Many Requests", {
        status: 429,
        headers: { "Retry-After": "45" },
      })
    );

    const client = new ApiClient(["http://host1:8000"]);
    try {
      const stream = client.ask({ question: "Test limit" });
      for await (const _ of stream) {}
      expect.fail("Should have thrown ApiError");
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.kind).toBe("rate_limited");
      expect(err.retryAfterSeconds).toBe(45);
    }
  });

  it("throws typed ApiError for 503 waking up", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Loading models", stage: "loading_models" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      })
    );

    const client = new ApiClient(["http://host1:8000"]);
    try {
      const stream = client.ask({ question: "Test waking" });
      for await (const _ of stream) {}
      expect.fail("Should have thrown ApiError");
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.kind).toBe("waking_up");
    }
  });
});
