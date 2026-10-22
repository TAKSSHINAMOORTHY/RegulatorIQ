/**
 * Pure conversation state reducer for RegulatorIQ.
 * Transitions deterministically through lifecycle stages and is fully replayable from an event list.
 */

import type { AgentEvent } from "./generated/events";

export type ConversationStatus =
  | "idle"
  | "waking"
  | "searching"
  | "checking_validity"
  | "verifying"
  | "streaming"
  | "done"
  | "refused"
  | "clarifying"
  | "error"
  | "cancelled";

export interface TimelineStep {
  id: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  timestamp?: number;
}

export interface CitationItem {
  id: string | number;
  index: number;
  title: string;
  circularNumber?: string;
  issueDate?: string;
  docType?: string;
  statusStamp?: "CURRENT" | "SUPERSEDED" | "AS AMENDED" | "UNCLEAR";
  supersededBy?: string;
  amendedBy?: string;
  excerpt?: string;
  url?: string;
}

export interface GroundingInfo {
  supportedClaims: number;
  totalClaims: number;
  judge?: string;
  statusText?: string;
}

export interface MessageState {
  id: string;
  question: string;
  answerText: string;
  status: ConversationStatus;
  timeline: TimelineStep[];
  citations: CitationItem[];
  validityNotes: string[];
  grounding?: GroundingInfo;
  requestId?: string;
  mode?: string;
  flags: {
    degraded?: boolean;
    lightMode?: boolean;
  };
  refusal?: {
    reason: string;
    relatedDocs?: string[];
  };
  clarification?: {
    question: string;
    options: string[];
  };
  error?: string;
}

export interface ConversationState {
  status: ConversationStatus;
  activeMessageIndex: number;
  messages: MessageState[];
}

export const initialConversationState: ConversationState = {
  status: "idle",
  activeMessageIndex: -1,
  messages: [],
};

export type Action =
  | { type: "START_ASK"; question: string; messageId?: string }
  | { type: "SET_WAKING"; message?: string }
  | { type: "CANCEL" }
  | { type: "RESET" }
  | { type: "APPLY_EVENT"; event: AgentEvent };

export function conversationReducer(
  state: ConversationState,
  action: Action
): ConversationState {
  switch (action.type) {
    case "START_ASK": {
      const newMessageId = action.messageId || `msg_${Date.now()}`;
      const defaultTimeline: TimelineStep[] = [
        { id: "search", label: "Searching official RBI documents", status: "running" },
        { id: "validity", label: "Checking whether the rule is still in force", status: "pending" },
        { id: "verify", label: "Verifying against sources", status: "pending" },
      ];

      const newMessage: MessageState = {
        id: newMessageId,
        question: action.question,
        answerText: "",
        status: "searching",
        timeline: defaultTimeline,
        citations: [],
        validityNotes: [],
        flags: {},
      };

      return {
        ...state,
        status: "searching",
        activeMessageIndex: state.messages.length,
        messages: [...state.messages, newMessage],
      };
    }

    case "SET_WAKING": {
      return {
        ...state,
        status: "waking",
      };
    }

    case "CANCEL": {
      if (state.activeMessageIndex < 0 || state.activeMessageIndex >= state.messages.length) {
        return { ...state, status: "cancelled" };
      }
      const updatedMessages = [...state.messages];
      const cur = { ...updatedMessages[state.activeMessageIndex] };
      cur.status = "cancelled";
      updatedMessages[state.activeMessageIndex] = cur;
      return {
        ...state,
        status: "cancelled",
        messages: updatedMessages,
      };
    }

    case "RESET": {
      return initialConversationState;
    }

    case "APPLY_EVENT": {
      if (state.activeMessageIndex < 0 || state.activeMessageIndex >= state.messages.length) {
        return state;
      }

      const updatedMessages = [...state.messages];
      const cur = { ...updatedMessages[state.activeMessageIndex] };
      const ev = action.event;
      const data = (ev.data || {}) as Record<string, any>;

      switch (ev.type) {
        case "meta": {
          if (data.request_id) cur.requestId = String(data.request_id);
          if (data.mode) cur.mode = String(data.mode);
          if (data.degraded) cur.flags.degraded = Boolean(data.degraded);
          break;
        }

        case "status": {
          const stepName = ev.step || String(data.step || "");
          if (stepName === "validity" || stepName.includes("validity")) {
            cur.timeline = cur.timeline.map((t) =>
              t.id === "search" ? { ...t, status: "completed" } : t.id === "validity" ? { ...t, status: "running" } : t
            );
            cur.status = "checking_validity";
          } else if (stepName === "xref" || stepName === "verify" || stepName.includes("grounding")) {
            cur.timeline = cur.timeline.map((t) =>
              t.id === "validity" ? { ...t, status: "completed" } : t.id === "verify" ? { ...t, status: "running" } : t
            );
            cur.status = "verifying";
          }
          break;
        }

        case "validity": {
          if (Array.isArray(data.validity_notes)) {
            cur.validityNotes = [...cur.validityNotes, ...data.validity_notes];
          }
          break;
        }

        case "grounding": {
          cur.grounding = {
            supportedClaims: Number(data.supported_claims ?? data.claims_supported ?? 0),
            totalClaims: Number(data.total_claims ?? 0),
            judge: String(data.judge ?? "deterministic"),
            statusText: data.summary ? String(data.summary) : undefined,
          };
          cur.timeline = cur.timeline.map((t) => (t.id === "verify" ? { ...t, status: "completed" } : t));
          break;
        }

        case "token": {
          const delta = String(data.delta ?? data.text ?? "");
          cur.answerText += delta;
          cur.status = "streaming";
          // Mark timeline steps complete once tokens start
          cur.timeline = cur.timeline.map((t) => ({ ...t, status: "completed" }));
          break;
        }

        case "citation": {
          const newCitation: CitationItem = {
            id: data.id ?? cur.citations.length + 1,
            index: cur.citations.length + 1,
            title: String(data.title || "RBI Notification"),
            circularNumber: data.circular_number || data.circular_no,
            issueDate: data.issue_date || data.date,
            docType: data.doc_type || "Circular",
            statusStamp: (data.status_stamp || data.validity || "CURRENT").toUpperCase() as any,
            supersededBy: data.superseded_by,
            amendedBy: data.amended_by,
            excerpt: data.excerpt || data.snippet,
            url: data.url,
          };
          cur.citations = [...cur.citations, newCitation];
          break;
        }

        case "refusal": {
          cur.status = "refused";
          cur.refusal = {
            reason: String(data.reason || "Query refused under regulatory safety policies."),
            relatedDocs: Array.isArray(data.related_docs) ? data.related_docs : [],
          };
          cur.timeline = cur.timeline.map((t) => ({ ...t, status: "completed" }));
          break;
        }

        case "clarification": {
          cur.status = "clarifying";
          cur.clarification = {
            question: String(data.question || "Please clarify your request:"),
            options: Array.isArray(data.options) ? data.options : [],
          };
          cur.timeline = cur.timeline.map((t) => ({ ...t, status: "completed" }));
          break;
        }

        case "done": {
          cur.status = "done";
          if (data.answer && !cur.answerText) {
            cur.answerText = String(data.answer);
          }
          if (Array.isArray(data.citations) && cur.citations.length === 0) {
            cur.citations = data.citations.map((c: any, idx: number) => ({
              id: c.id ?? idx + 1,
              index: idx + 1,
              title: c.title || "Official RBI Circular",
              circularNumber: c.circular_number,
              issueDate: c.issue_date,
              docType: c.doc_type || "Circular",
              statusStamp: (c.status_stamp || "CURRENT").toUpperCase() as any,
              supersededBy: c.superseded_by,
              amendedBy: c.amended_by,
              excerpt: c.excerpt || c.snippet,
              url: c.url,
            }));
          }
          cur.timeline = cur.timeline.map((t) => ({ ...t, status: "completed" }));
          break;
        }

        case "error": {
          cur.status = "error";
          cur.error = String(data.error || data.detail || "An unexpected error occurred during processing.");
          cur.timeline = cur.timeline.map((t) =>
            t.status === "running" ? { ...t, status: "failed" } : t
          );
          break;
        }
      }

      updatedMessages[state.activeMessageIndex] = cur;
      return {
        ...state,
        status: cur.status,
        messages: updatedMessages,
      };
    }

    default:
      return state;
  }
}

/**
 * Replays a list of events to reconstitute state deterministically.
 */
export function replayEvents(events: AgentEvent[], question = "Test Question"): ConversationState {
  let st = conversationReducer(initialConversationState, { type: "START_ASK", question });
  for (const ev of events) {
    st = conversationReducer(st, { type: "APPLY_EVENT", event: ev });
  }
  return st;
}
