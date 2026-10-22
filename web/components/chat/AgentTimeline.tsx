"use client";

import React, { useState } from "react";
import { CheckCircle2, CircleDashed, ChevronDown, ChevronRight, AlertCircle } from "lucide-react";
import type { TimelineStep } from "@/lib/reducer";

interface AgentTimelineProps {
  timeline: TimelineStep[];
  isDone: boolean;
  statusText?: string;
}

export function AgentTimeline({ timeline, isDone, statusText }: AgentTimelineProps) {
  const [expanded, setExpanded] = useState(!isDone);

  if (timeline.length === 0) return null;

  const completedCount = timeline.filter((t) => t.status === "completed").length;
  const runningStep = timeline.find((t) => t.status === "running");

  return (
    <div className="my-2 border border-line rounded-lg bg-surface-2/40 overflow-hidden text-xs sm:text-sm">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-muted hover:text-ink hover:bg-surface-2/70 transition-colors"
        aria-expanded={expanded}
      >
        <div className="flex items-center space-x-2">
          {isDone ? (
            <CheckCircle2 className="w-4 h-4 text-success" />
          ) : (
            <CircleDashed className="w-4 h-4 text-accent animate-spin" />
          )}
          <span className="font-medium text-ink">
            {isDone
              ? "Synthesis verified against official RBI sources"
              : runningStep?.label || statusText || "Processing query..."}
          </span>
          <span className="text-muted text-xs">
            ({completedCount}/{timeline.length})
          </span>
        </div>
        {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>

      {expanded && (
        <div className="px-3 pb-2.5 pt-1 space-y-2 border-t border-line/50">
          {timeline.map((step) => {
            const isCompleted = step.status === "completed";
            const isRunning = step.status === "running";
            const isFailed = step.status === "failed";

            return (
              <div key={step.id} className="flex items-center space-x-2.5">
                {isCompleted ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />
                ) : isRunning ? (
                  <CircleDashed className="w-3.5 h-3.5 text-accent animate-spin shrink-0" />
                ) : isFailed ? (
                  <AlertCircle className="w-3.5 h-3.5 text-danger shrink-0" />
                ) : (
                  <div className="w-3.5 h-3.5 rounded-full border border-line shrink-0" />
                )}
                <span
                  className={`${
                    isCompleted
                      ? "text-muted line-through"
                      : isRunning
                      ? "text-accent-text font-semibold"
                      : "text-muted"
                  }`}
                >
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
