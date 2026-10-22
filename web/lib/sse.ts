/**
 * SSE Parser using fetch + ReadableStream.
 * Handles split chunks at arbitrary byte boundaries, CRLF/LF, comments, multi-line data, and heartbeats.
 */

import type { AgentEvent } from "./generated/events";

export interface SSEMessage {
  id?: string;
  event?: string;
  data: string;
}

export interface ParseSSEOptions {
  onEvent: (event: AgentEvent) => void;
  onError?: (err: Error) => void;
  onComment?: (comment: string) => void;
  signal?: AbortSignal;
}

export async function parseSSEStream(
  stream: ReadableStream<Uint8Array>,
  options: ParseSSEOptions
): Promise<{ unknownEventsCount: number }> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let unknownEventsCount = 0;

  let currentId: string | undefined;
  let currentEvent: string | undefined;
  let currentDataParts: string[] = [];

  const dispatchCurrentMessage = () => {
    if (currentDataParts.length === 0 && !currentEvent) {
      return;
    }
    const rawData = currentDataParts.join("\n");
    currentDataParts = [];

    if (!rawData.trim()) {
      return;
    }

    try {
      const parsed = JSON.parse(rawData);
      // Validate or tag event type if provided
      if (currentEvent && typeof parsed === "object" && parsed !== null && !parsed.type) {
        parsed.type = currentEvent;
      }
      options.onEvent(parsed as AgentEvent);
    } catch (err) {
      if (options.onError) {
        options.onError(new Error(`Malformed SSE JSON payload: ${rawData}`));
      }
    }
    currentEvent = undefined;
  };

  try {
    while (true) {
      if (options.signal?.aborted) {
        break;
      }

      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(/\r?\n/);
      // Keep the last partial line in the buffer
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.trim() === "") {
          // Empty line signals message dispatch
          dispatchCurrentMessage();
          continue;
        }

        if (line.startsWith(":")) {
          // Comment or heartbeat (e.g., ": ping")
          if (options.onComment) {
            options.onComment(line.slice(1).trim());
          }
          continue;
        }

        const colonIdx = line.indexOf(":");
        let field = line;
        let val = "";
        if (colonIdx !== -1) {
          field = line.slice(0, colonIdx);
          val = line.slice(colonIdx + 1);
          if (val.startsWith(" ")) {
            val = val.slice(1);
          }
        }

        if (field === "event") {
          currentEvent = val;
        } else if (field === "data") {
          currentDataParts.push(val);
        } else if (field === "id") {
          currentId = val;
        } else {
          unknownEventsCount++;
        }
      }
    }

    // Flush any trailing line in buffer
    if (buffer.trim()) {
      if (buffer.startsWith("data:")) {
        currentDataParts.push(buffer.slice(5).trim());
      }
      dispatchCurrentMessage();
    }
  } finally {
    reader.releaseLock();
  }

  return { unknownEventsCount };
}
