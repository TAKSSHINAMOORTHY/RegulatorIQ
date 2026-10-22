"use client";

import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Copy, Check, History } from "lucide-react";
import { defaultApiClient } from "@/lib/apiClient";
import type { CitationItem } from "@/lib/reducer";

interface FeedbackControlProps {
  requestId?: string;
  answerText: string;
  citations: CitationItem[];
  hasSuperseded?: boolean;
  onAskHistorical?: () => void;
}

export function FeedbackControl({
  requestId,
  answerText,
  citations,
  hasSuperseded,
  onAskHistorical,
}: FeedbackControlProps) {
  const [copied, setCopied] = useState(false);
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [showReasonPicker, setShowReasonPicker] = useState(false);
  const [submittedReason, setSubmittedReason] = useState<string | null>(null);

  const copyWithCitations = () => {
    let fullText = answerText;
    if (citations.length > 0) {
      fullText += "\n\nSources:\n";
      citations.forEach((c) => {
        fullText += `[${c.index}] ${c.title}${c.circularNumber ? ` (${c.circularNumber})` : ""}${
          c.url ? ` - ${c.url}` : ""
        }\n`;
      });
    }

    navigator.clipboard.writeText(fullText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleUpvote = async () => {
    setRating("up");
    setShowReasonPicker(false);
    if (!requestId) return;
    try {
      await defaultApiClient.feedback({
        request_id: requestId,
        rating: "up",
      });
    } catch {
      // Graceful catch
    }
  };

  const handleDownvote = () => {
    setRating("down");
    setShowReasonPicker(true);
  };

  const submitReason = async (reason: string) => {
    setSubmittedReason(reason);
    setShowReasonPicker(false);
    if (!requestId) return;
    try {
      await defaultApiClient.feedback({
        request_id: requestId,
        rating: "down",
        comment: reason,
      });
    } catch {
      // Graceful catch
    }
  };

  return (
    <div className="pt-2 border-t border-line/60 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
      <div className="flex items-center space-x-2">
        <button
          onClick={copyWithCitations}
          aria-label="Copy answer with citations"
          className="p-1.5 rounded hover:bg-surface-2 text-muted hover:text-ink transition-colors inline-flex items-center space-x-1"
          title="Copy answer with citations"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>

        <div className="h-3 w-px bg-line mx-1" />

        <button
          onClick={handleUpvote}
          aria-label="Helpful answer"
          className={`p-1.5 rounded transition-colors ${
            rating === "up" ? "text-success bg-success/10 font-bold" : "hover:bg-surface-2 hover:text-ink"
          }`}
          title="Helpful"
        >
          <ThumbsUp className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={handleDownvote}
          aria-label="Inaccurate or unhelpful answer"
          className={`p-1.5 rounded transition-colors ${
            rating === "down" ? "text-danger bg-danger/10 font-bold" : "hover:bg-surface-2 hover:text-ink"
          }`}
          title="Inaccurate or unhelpful"
        >
          <ThumbsDown className="w-3.5 h-3.5" />
        </button>

        {showReasonPicker && (
          <div className="flex items-center space-x-1 pl-2">
            <span className="text-muted">Issue:</span>
            {["Outdated rule", "Missing citation", "Hallucination", "Incomplete"].map((reason) => (
              <button
                key={reason}
                onClick={() => submitReason(reason)}
                className="px-2 py-0.5 rounded bg-surface border border-line hover:border-accent text-ink text-xs transition-colors"
              >
                {reason}
              </button>
            ))}
          </div>
        )}

        {submittedReason && (
          <span className="text-success text-xs">Feedback received</span>
        )}
      </div>

      {hasSuperseded && onAskHistorical && (
        <button
          onClick={onAskHistorical}
          className="text-accent-text hover:text-accent font-medium inline-flex items-center space-x-1 hover:underline"
        >
          <History className="w-3.5 h-3.5" />
          <span>Ask again including historical rules</span>
        </button>
      )}
    </div>
  );
}
