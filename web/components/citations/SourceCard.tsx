"use client";

import React, { useState } from "react";
import { Copy, Check, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import type { CitationItem } from "@/lib/reducer";

interface SourceCardProps {
  citation: CitationItem;
  isActive?: boolean;
}

export function isAllowedRbiUrl(url?: string): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    return host === "rbi.org.in" || host.endsWith(".rbi.org.in");
  } catch {
    return false;
  }
}

export function SourceCard({ citation, isActive }: SourceCardProps) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const copyCircularNo = () => {
    if (!citation.circularNumber) return;
    navigator.clipboard.writeText(citation.circularNumber).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const stampColor =
    citation.statusStamp === "CURRENT"
      ? "text-success border-success"
      : citation.statusStamp === "SUPERSEDED"
      ? "text-danger border-danger"
      : citation.statusStamp === "AS AMENDED"
      ? "text-warning border-warning"
      : "text-muted border-line";

  const isRbiLink = isAllowedRbiUrl(citation.url);

  return (
    <div
      id={`source-card-${citation.index}`}
      tabIndex={0}
      aria-label={`Source citation ${citation.index}: ${citation.title}. Status: ${citation.statusStamp || "CURRENT"}`}
      className={`p-3.5 rounded-lg border transition-all text-xs sm:text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring ${
        isActive
          ? "border-accent bg-accent/5 ring-1 ring-accent"
          : "border-line bg-surface hover:border-accent/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center space-x-2">
          <span className="w-5 h-5 rounded-full bg-accent text-white flex items-center justify-center font-mono text-xs font-bold">
            {citation.index}
          </span>
          <span className="font-semibold text-ink line-clamp-1">{citation.title}</span>
        </div>

        {/* Inked-corner status stamp */}
        <span className={`status-stamp ${stampColor}`}>
          {citation.statusStamp || "CURRENT"}
        </span>
      </div>

      {/* Circular number and issue date */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {citation.circularNumber && (
          <div className="flex items-center space-x-1">
            <span className="font-mono text-ink font-medium">{citation.circularNumber}</span>
            <button
              onClick={copyCircularNo}
              aria-label="Copy circular number"
              className="p-1 hover:text-ink transition-colors"
              title="Copy identifier"
            >
              {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
        )}
        {citation.issueDate && <span>Date: {citation.issueDate}</span>}
        {citation.docType && <span>Type: {citation.docType}</span>}
      </div>

      {/* Superseded / Amended notes */}
      {citation.supersededBy && (
        <div className="mt-2 p-2 rounded bg-danger/10 border border-danger/30 text-danger text-xs">
          <strong>Superseded by:</strong> {citation.supersededBy}
        </div>
      )}
      {citation.amendedBy && (
        <div className="mt-2 p-2 rounded bg-warning/10 border border-warning/30 text-warning text-xs">
          <strong>Amended by:</strong> {citation.amendedBy}
        </div>
      )}

      {/* Excerpt quote */}
      {citation.excerpt && (
        <div className="mt-2 text-muted italic bg-surface-2/50 p-2 rounded border border-line/40">
          <p className={expanded ? "" : "line-clamp-2"}>
            &ldquo;{citation.excerpt}&rdquo;
          </p>
          {citation.excerpt.length > 120 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-1 text-accent font-medium inline-flex items-center text-xs hover:underline"
            >
              {expanded ? (
                <>
                  Show less <ChevronUp className="w-3 h-3 ml-0.5" />
                </>
              ) : (
                <>
                  Show more <ChevronDown className="w-3 h-3 ml-0.5" />
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* External Link (Strict RBI whitelist) */}
      {citation.url && (
        <div className="mt-2.5 pt-2 border-t border-line/50 flex justify-end">
          {isRbiLink ? (
            <a
              href={citation.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1 text-xs text-accent-text hover:text-accent font-medium hover:underline"
            >
              <span>Open on rbi.org.in</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          ) : (
            <span className="text-xs text-muted font-mono">{citation.url}</span>
          )}
        </div>
      )}
    </div>
  );
}
