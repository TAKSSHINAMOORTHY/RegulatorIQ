/**
 * API Client for RegulatorIQ with multi-host failover, health probing, typed errors, and SSE streaming.
 */

import { parseSSEStream } from "./sse";
import type { AgentEvent } from "./generated/events";
import type { components } from "./generated/openapi";

export type AskRequest = components["schemas"]["AskRequest"];
export type FeedbackRequest = components["schemas"]["FeedbackRequest"];
export type MetaResponse = components["schemas"]["MetaResponse"];
export type ReadyResponse = components["schemas"]["ReadyResponse"];

export type ApiErrorKind =
  | "rate_limited"
  | "busy"
  | "waking_up"
  | "offline"
  | "server_error"
  | "refused_by_guard";

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  retryAfterSeconds?: number;
  stage?: string;

  constructor(message: string, kind: ApiErrorKind, status?: number, retryAfterSeconds?: number, stage?: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
    this.stage = stage;
  }
}

interface HealthCacheEntry {
  healthy: boolean;
  timestamp: number;
}

export class ApiClient {
  private urls: string[];
  private healthCache: Map<string, HealthCacheEntry> = new Map();
  private activeUrlIndex = 0;

  constructor(urls?: string[] | string) {
    if (typeof urls === "string") {
      this.urls = urls.split(",").map((u) => u.trim().replace(/\/$/, "")).filter(Boolean);
    } else if (Array.isArray(urls) && urls.length > 0) {
      this.urls = urls.map((u) => u.trim().replace(/\/$/, "")).filter(Boolean);
    } else {
      const envUrls = process.env.NEXT_PUBLIC_API_URLS || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      this.urls = envUrls.split(",").map((u) => u.trim().replace(/\/$/, "")).filter(Boolean);
    }

    if (this.urls.length === 0) {
      this.urls = ["http://localhost:8000"];
    }
  }

  public getUrls(): string[] {
    return [...this.urls];
  }

  public getActiveUrl(): string {
    return this.urls[this.activeUrlIndex] || this.urls[0];
  }

  public async checkHealth(baseUrl: string): Promise<boolean> {
    const cached = this.healthCache.get(baseUrl);
    const now = Date.now();
    if (cached && now - cached.timestamp < 60_000) {
      return cached.healthy;
    }

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3000);
      const res = await fetch(`${baseUrl}/health`, {
        method: "GET",
        signal: controller.signal,
      });
      clearTimeout(timer);
      const healthy = res.ok;
      this.healthCache.set(baseUrl, { healthy, timestamp: now });
      return healthy;
    } catch {
      this.healthCache.set(baseUrl, { healthy: false, timestamp: now });
      return false;
    }
  }

  public async pickHealthyUrl(): Promise<string> {
    for (let i = 0; i < this.urls.length; i++) {
      const url = this.urls[i];
      const healthy = await this.checkHealth(url);
      if (healthy) {
        this.activeUrlIndex = i;
        return url;
      }
    }
    // If none respond to /health, return primary to let request reveal exact error state
    return this.urls[0];
  }

  public async getReady(baseUrl?: string): Promise<ReadyResponse> {
    const url = baseUrl || (await this.pickHealthyUrl());
    try {
      const res = await fetch(`${url}/ready`, { method: "GET" });
      if (res.status === 503) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(
          body.detail || "Server is warming up or loading index",
          "waking_up",
          503,
          undefined,
          body.stage || "starting"
        );
      }
      if (!res.ok) {
        throw new ApiError(`Ready check failed with ${res.status}`, "server_error", res.status);
      }
      return (await res.json()) as ReadyResponse;
    } catch (err: any) {
      if (err instanceof ApiError) throw err;
      throw new ApiError("Failed to connect to ready endpoint", "offline");
    }
  }

  public async getMeta(baseUrl?: string): Promise<MetaResponse> {
    const url = baseUrl || (await this.pickHealthyUrl());
    try {
      const res = await fetch(`${url}/meta`, { method: "GET" });
      if (!res.ok) {
        throw new ApiError(`Meta check failed with ${res.status}`, "server_error", res.status);
      }
      return (await res.json()) as MetaResponse;
    } catch (err: any) {
      if (err instanceof ApiError) throw err;
      throw new ApiError("Failed to fetch meta information", "offline");
    }
  }

  public async *ask(request: AskRequest, signal?: AbortSignal): AsyncIterable<AgentEvent> {
    let attempt = 0;
    const maxAttempts = Math.min(2, this.urls.length);
    let startIdx = this.activeUrlIndex;
    let tokensReceived = false;

    while (attempt < maxAttempts) {
      const targetUrl = this.urls[(startIdx + attempt) % this.urls.length];
      attempt++;

      let response: Response;
      try {
        response = await fetch(`${targetUrl}/ask`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(request),
          signal,
        });
      } catch (err: any) {
        if (signal?.aborted) {
          throw err;
        }
        if (attempt < maxAttempts) {
          continue; // Failover before any tokens arrived
        }
        throw new ApiError("Network connection refused or unreachable", "offline");
      }

      if (response.status === 429) {
        const retryHeader = response.headers.get("Retry-After");
        const retrySec = retryHeader ? parseInt(retryHeader, 10) : 60;
        throw new ApiError("Rate limit reached", "rate_limited", 429, retrySec);
      }

      if (response.status === 503) {
        const body = await response.json().catch(() => ({}));
        if (body.detail === "System busy") {
          throw new ApiError("Server is currently handling peak traffic", "busy", 503);
        }
        if (attempt < maxAttempts) {
          continue; // Failover to secondary
        }
        throw new ApiError(body.detail || "Server waking up", "waking_up", 503, undefined, body.stage);
      }

      if (response.status >= 500) {
        if (attempt < maxAttempts) {
          continue; // Failover once
        }
        throw new ApiError(`Server error (${response.status})`, "server_error", response.status);
      }

      if (response.status === 400 || response.status === 422) {
        const body = await response.json().catch(() => ({}));
        throw new ApiError(body.detail || "Invalid request payload", "refused_by_guard", response.status);
      }

      if (!response.body) {
        throw new ApiError("Empty response body received from server", "server_error");
      }

      // Stream events through queue
      const eventQueue: AgentEvent[] = [];
      let streamError: Error | null = null;
      let streamDone = false;
      let resolveWait: (() => void) | null = null;

      const notify = () => {
        if (resolveWait) {
          const fn = resolveWait;
          resolveWait = null;
          fn();
        }
      };

      const parsePromise = parseSSEStream(response.body, {
        signal,
        onEvent: (event) => {
          if (event.type === "token") {
            tokensReceived = true;
          }
          eventQueue.push(event);
          notify();
        },
        onError: (err) => {
          streamError = err;
          notify();
        },
      })
        .then(() => {
          streamDone = true;
          notify();
        })
        .catch((err) => {
          streamError = err;
          streamDone = true;
          notify();
        });

      while (!streamDone || eventQueue.length > 0) {
        if (eventQueue.length > 0) {
          const ev = eventQueue.shift()!;
          yield ev;
        } else if (streamError) {
          throw streamError;
        } else if (!streamDone) {
          await new Promise<void>((r) => {
            resolveWait = r;
          });
        }
      }

      await parsePromise;
      return;
    }
  }

  public async askJson(request: AskRequest, signal?: AbortSignal): Promise<any> {
    const url = await this.pickHealthyUrl();
    const res = await fetch(`${url}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(request),
      signal,
    });
    if (!res.ok) {
      if (res.status === 429) {
        const retryHeader = res.headers.get("Retry-After");
        throw new ApiError("Rate limit reached", "rate_limited", 429, retryHeader ? parseInt(retryHeader, 10) : 60);
      }
      throw new ApiError(`Request failed with status ${res.status}`, "server_error", res.status);
    }
    return res.json();
  }

  public async feedback(request: FeedbackRequest, signal?: AbortSignal): Promise<{ status: string }> {
    const url = await this.pickHealthyUrl();
    const res = await fetch(`${url}/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      signal,
    });
    if (!res.ok) {
      throw new ApiError(`Feedback submission failed with ${res.status}`, "server_error", res.status);
    }
    return res.json();
  }
}

export const defaultApiClient = new ApiClient();
