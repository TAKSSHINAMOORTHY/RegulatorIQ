"use client";

import React from "react";

interface MarkdownAnswerProps {
  content: string;
  onCitationClick?: (index: number) => void;
  activeCitation?: number | null;
}

/**
 * Safe markdown subset renderer (no dangerouslySetInnerHTML, HTML tags disabled).
 * Parses headings, lists, bold/italic, inline code, blockquotes, tables, and replaces [n] with interactive citation chips.
 */
export function MarkdownAnswer({ content, onCitationClick, activeCitation }: MarkdownAnswerProps) {
  if (!content) return null;

  // Split by double newline into block segments
  const blocks = content.split(/\n\n+/);

  const renderInline = (text: string): React.ReactNode[] => {
    // Replace citation markers like [1], [2] with chips
    const parts = text.split(/(\[\d+\]|\*\*.*?\*\*|\*.*?\*|`.*?`)/g);

    return parts.map((part, idx) => {
      if (!part) return null;

      // Citation marker: [1]
      const citMatch = part.match(/^\[(\d+)\]$/);
      if (citMatch) {
        const num = parseInt(citMatch[1], 10);
        const isActive = activeCitation === num;
        return (
          <button
            key={`cit_${idx}`}
            type="button"
            onClick={() => onCitationClick?.(num)}
            aria-label={`Jump to citation [${num}]`}
            className={`citation-tab mx-0.5 px-1.5 py-0.5 text-xs font-mono rounded cursor-pointer transition-colors ${
              isActive
                ? "bg-accent text-white border-accent"
                : "bg-surface-2 text-accent-text hover:bg-accent/15"
            }`}
          >
            [{num}]
          </button>
        );
      }

      // Bold: **text**
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={idx} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
      }

      // Italic: *text*
      if (part.startsWith("*") && part.endsWith("*")) {
        return <em key={idx} className="italic">{part.slice(1, -1)}</em>;
      }

      // Code: `code`
      if (part.startsWith("`") && part.endsWith("`")) {
        return (
          <code
            key={idx}
            className="px-1.5 py-0.5 rounded bg-surface-2 font-mono text-xs border border-line text-ink"
          >
            {part.slice(1, -1)}
          </code>
        );
      }

      // Plain text (strips raw html brackets for safety)
      const sanitized = part.replace(/[<>]/g, "");
      return <React.Fragment key={idx}>{sanitized}</React.Fragment>;
    });
  };

  return (
    <div className="space-y-3 leading-relaxed text-ink text-sm sm:text-base font-sans">
      {blocks.map((block, bIdx) => {
        const lines = block.split(/\n/).map((l) => l.trim());

        // Blockquote
        if (lines[0]?.startsWith(">")) {
          const quoteText = lines.map((l) => l.replace(/^>\s*/, "")).join(" ");
          return (
            <blockquote
              key={bIdx}
              className="border-l-4 border-accent pl-4 py-1 italic text-muted bg-surface-2/40 rounded-r"
            >
              {renderInline(quoteText)}
            </blockquote>
          );
        }

        // Unordered list
        if (lines.every((l) => l.startsWith("- ") || l.startsWith("* "))) {
          return (
            <ul key={bIdx} className="list-disc pl-5 space-y-1.5">
              {lines.map((l, lIdx) => (
                <li key={lIdx}>{renderInline(l.replace(/^[-*]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }

        // Ordered list
        if (lines.every((l) => /^\d+\.\s+/.test(l))) {
          return (
            <ol key={bIdx} className="list-decimal pl-5 space-y-1.5">
              {lines.map((l, lIdx) => (
                <li key={lIdx}>{renderInline(l.replace(/^\d+\.\s+/, ""))}</li>
              ))}
            </ol>
          );
        }

        // Heading: ###
        if (lines[0]?.startsWith("### ")) {
          return (
            <h4 key={bIdx} className="font-serif font-bold text-base sm:text-lg text-ink pt-1">
              {renderInline(lines[0].slice(4))}
            </h4>
          );
        }
        if (lines[0]?.startsWith("## ")) {
          return (
            <h3 key={bIdx} className="font-serif font-bold text-lg sm:text-xl text-ink pt-2">
              {renderInline(lines[0].slice(3))}
            </h3>
          );
        }

        // Paragraph
        return <p key={bIdx}>{renderInline(block)}</p>;
      })}
    </div>
  );
}
