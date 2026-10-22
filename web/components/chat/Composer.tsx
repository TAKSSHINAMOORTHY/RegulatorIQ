"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Square, SlidersHorizontal } from "lucide-react";

interface ComposerProps {
  onSend: (question: string, options?: { asOfDate?: string; includeSuperseded?: boolean }) => void;
  onStop?: () => void;
  isStreaming?: boolean;
  disabled?: boolean;
  disabledReason?: string;
}

const MAX_CHARS = 1000;

export function Composer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  disabledReason,
}: ComposerProps) {
  const [text, setText] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const [asOfDate, setAsOfDate] = useState("");
  const [pasteNotice, setPasteNotice] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // "/" focuses from anywhere
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        textareaRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Auto-grow textarea up to 6 lines (~144px)
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        150,
        textareaRef.current.scrollHeight
      )}px`;
    }
  }, [text]);

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text");
    // Strip control chars except \n and \t
    const sanitized = pasted.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
    if (sanitized.length > MAX_CHARS) {
      setPasteNotice(true);
      setTimeout(() => setPasteNotice(false), 3000);
    }
    const truncated = sanitized.slice(0, MAX_CHARS);
    setText((prev) => (prev + truncated).slice(0, MAX_CHARS));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming || disabled) return;
    onSend(trimmed, {
      asOfDate: asOfDate || undefined,
      includeSuperseded,
    });
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const charCount = text.length;
  const showCounter = charCount >= MAX_CHARS * 0.8;

  return (
    <div className="w-full relative">
      {pasteNotice && (
        <div className="mb-2 p-2 rounded bg-warning/15 border border-warning/30 text-warning text-xs">
          Pasted text exceeded {MAX_CHARS} characters and was trimmed.
        </div>
      )}

      {disabledReason && (
        <div className="mb-2 p-2 rounded bg-surface-2 border border-line text-muted text-xs">
          {disabledReason}
        </div>
      )}

      {/* Filter Popover */}
      {showFilters && (
        <div className="absolute bottom-full mb-2 left-0 w-72 p-3.5 rounded-xl border border-line bg-surface shadow-lg space-y-3 z-30">
          <div className="flex items-center justify-between pb-1 border-b border-line">
            <span className="font-serif font-bold text-xs text-ink">Query Filters</span>
            <button
              onClick={() => setShowFilters(false)}
              className="text-muted hover:text-ink text-xs"
            >
              Close
            </button>
          </div>
          <label className="flex items-center space-x-2 text-xs text-ink cursor-pointer">
            <input
              type="checkbox"
              checked={includeSuperseded}
              onChange={(e) => setIncludeSuperseded(e.target.checked)}
              className="rounded border-line text-accent focus:ring-focus-ring"
            />
            <span>Include historical / superseded rules</span>
          </label>
          <div>
            <label className="block text-xs text-muted mb-1">As-Of Date (YYYY-MM-DD):</label>
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="w-full px-2 py-1 text-xs rounded border border-line bg-surface-2 text-ink"
            />
          </div>
        </div>
      )}

      <div className="relative rounded-2xl border border-line bg-surface shadow-md hover:border-accent/40 focus-within:border-accent focus-within:ring-2 focus-within:ring-focus-ring transition-all">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          disabled={disabled}
          placeholder="Ask a regulatory question (e.g. capital adequacy, liquidity, KYC norms)... (Press / to focus)"
          rows={1}
          className="w-full resize-none bg-transparent py-3.5 pl-4 pr-24 text-sm sm:text-base text-ink placeholder:text-muted focus:outline-none max-h-36"
        />

        {/* Action buttons inside composer */}
        <div className="absolute right-2.5 bottom-2.5 flex items-center space-x-1.5">
          {showCounter && (
            <span className="text-xs font-mono text-muted mr-1">
              {charCount}/{MAX_CHARS}
            </span>
          )}

          <button
            type="button"
            onClick={() => setShowFilters(!showFilters)}
            aria-label="Filter options"
            title="Search options"
            className={`p-1.5 rounded-lg border transition-colors ${
              includeSuperseded || asOfDate
                ? "border-accent text-accent bg-accent/10"
                : "border-transparent text-muted hover:text-ink hover:bg-surface-2"
            }`}
          >
            <SlidersHorizontal className="w-4 h-4" />
          </button>

          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating answer"
              title="Stop generation"
              className="p-2 rounded-xl bg-danger text-white hover:bg-danger/90 transition-colors shadow-sm"
            >
              <Square className="w-4 h-4 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!text.trim() || disabled}
              aria-label="Send query"
              title="Send (Enter)"
              className="p-2 rounded-xl bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
