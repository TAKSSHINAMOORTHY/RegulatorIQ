import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiClient } from "@/lib/apiClient";

describe("ApiClient additional methods", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("fetches metadata successfully", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ index_version: "2024.10", mode: "full" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const client = new ApiClient(["http://localhost:8000"]);
    const meta = await client.getMeta();
    expect(meta.index_version).toBe("2024.10");
  });

  it("calls askJson successfully", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ answer: "Grounded answer" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const client = new ApiClient(["http://localhost:8000"]);
    const res = await client.askJson({ question: "JSON question" });
    expect(res.answer).toBe("Grounded answer");
  });

  it("submits feedback successfully", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "recorded" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const client = new ApiClient(["http://localhost:8000"]);
    const res = await client.feedback({ request_id: "req_1", rating: "up" });
    expect(res.status).toBe("recorded");
  });
});
