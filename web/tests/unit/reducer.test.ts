import { describe, it, expect } from "vitest";
import { conversationReducer, initialConversationState, replayEvents } from "@/lib/reducer";
import type { AgentEvent } from "@/lib/generated/events";

describe("Conversation State Reducer", () => {
  it("transitions through searching -> streaming -> done", () => {
    let state = conversationReducer(initialConversationState, {
      type: "START_ASK",
      question: "What is CRR?",
    });

    expect(state.status).toBe("searching");
    expect(state.messages.length).toBe(1);

    // Apply token event
    const tokenEvent: AgentEvent = {
      seq: 1,
      step: "generation",
      type: "token",
      data: { delta: "Cash Reserve Ratio is " },
    };
    state = conversationReducer(state, { type: "APPLY_EVENT", event: tokenEvent });
    expect(state.status).toBe("streaming");
    expect(state.messages[0].answerText).toBe("Cash Reserve Ratio is ");

    // Apply done event
    const doneEvent: AgentEvent = {
      seq: 2,
      step: "done",
      type: "done",
      data: {
        citations: [
          {
            title: "RBI Master Direction on CRR",
            circular_number: "RBI/2021-22/12",
            status_stamp: "CURRENT",
          },
        ],
      },
    };
    state = conversationReducer(state, { type: "APPLY_EVENT", event: doneEvent });
    expect(state.status).toBe("done");
    expect(state.messages[0].citations.length).toBe(1);
    expect(state.messages[0].citations[0].statusStamp).toBe("CURRENT");
  });

  it("replays recorded event stream deterministically", () => {
    const recordedEvents: AgentEvent[] = [
      { seq: 1, step: "init", type: "meta", data: { request_id: "req_123", mode: "full" } },
      { seq: 2, step: "validity", type: "status", data: { step: "validity" } },
      { seq: 3, step: "generation", type: "token", data: { delta: "Part 1. " } },
      { seq: 4, step: "generation", type: "token", data: { delta: "Part 2." } },
      {
        seq: 5,
        step: "grounding",
        type: "grounding",
        data: { supported_claims: 2, total_claims: 2, judge: "deterministic" },
      },
      { seq: 6, step: "done", type: "done", data: {} },
    ];

    const replayed = replayEvents(recordedEvents, "Test Question");
    expect(replayed.status).toBe("done");
    expect(replayed.messages[0].requestId).toBe("req_123");
    expect(replayed.messages[0].answerText).toBe("Part 1. Part 2.");
    expect(replayed.messages[0].grounding?.supportedClaims).toBe(2);
  });

  it("handles refusal event cleanly", () => {
    const refusalEvents: AgentEvent[] = [
      {
        seq: 1,
        step: "guard",
        type: "refusal",
        data: {
          reason: "Query outside RBI regulatory scope.",
          related_docs: ["FEMA Guidelines"],
        },
      },
    ];

    const state = replayEvents(refusalEvents, "Off topic query");
    expect(state.status).toBe("refused");
    expect(state.messages[0].refusal?.reason).toContain("outside RBI regulatory scope");
    expect(state.messages[0].refusal?.relatedDocs).toContain("FEMA Guidelines");
  });

  it("handles clarification event cleanly", () => {
    const clarEvents: AgentEvent[] = [
      {
        seq: 1,
        step: "router",
        type: "clarification",
        data: {
          question: "Did you mean Commercial Banks or Co-operative Banks?",
          options: ["Commercial Banks", "Co-operative Banks"],
        },
      },
    ];

    const state = replayEvents(clarEvents, "Capital norms");
    expect(state.status).toBe("clarifying");
    expect(state.messages[0].clarification?.options.length).toBe(2);
  });
});
