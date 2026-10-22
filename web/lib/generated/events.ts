/* eslint-disable */
/**
 * Auto-generated from agent/events.schema.json
 * DO NOT EDIT DIRECTLY.
 */

/**
 * Monotonically increasing sequence number (1-indexed)
 */
export type Seq = number;
/**
 * Unix epoch timestamp in seconds
 */
export type Ts = number;
/**
 * Agent node or lifecycle stage name
 */
export type Step = string;
/**
 * Event type from contract specification
 */
export type Type = string;

/**
 * Immutable event payload streamed to client.
 */
export interface AgentEvent {
  seq: Seq;
  ts?: Ts;
  step: Step;
  type: Type;
  data?: Data;
  [k: string]: unknown;
}
/**
 * Structured event payload
 */
export interface Data {
  [k: string]: unknown;
}
