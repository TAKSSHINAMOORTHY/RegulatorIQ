"use client";

import React from "react";
import { BookOpen, X } from "lucide-react";
import { SourceCard } from "./SourceCard";
import type { CitationItem } from "@/lib/reducer";

interface SourcesPanelProps {
  citations: CitationItem[];
  activeCitation?: number | null;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export function SourcesPanel({
  citations,
  activeCitation,
  isOpenMobile,
  onCloseMobile,
}: SourcesPanelProps) {
  if (citations.length === 0) {
    return (
      <div className="p-4 border border-line rounded-xl bg-surface-2/30 text-center text-muted text-xs sm:text-sm">
        <BookOpen className="w-6 h-6 mx-auto mb-2 opacity-40" />
        <p>No sources cited for this response yet.</p>
      </div>
    );
  }

  const content = (
    <div className="space-y-3">
      <div className="flex items-center justify-between pb-2 border-b border-line">
        <div className="flex items-center space-x-2">
          <BookOpen className="w-4 h-4 text-accent" />
          <h3 className="font-serif font-bold text-ink text-sm sm:text-base">
            Official Sources ({citations.length})
          </h3>
        </div>
        {onCloseMobile && (
          <button
            onClick={onCloseMobile}
            className="md:hidden p-1 text-muted hover:text-ink"
            aria-label="Close sources panel"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
        {citations.map((c) => (
          <SourceCard
            key={c.id || c.index}
            citation={c}
            isActive={activeCitation === c.index}
          />
        ))}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Panel */}
      <aside className="hidden lg:block w-80 shrink-0 sticky top-20 glass-surface p-4 rounded-xl shadow-sm">
        {content}
      </aside>

      {/* Mobile Bottom Sheet */}
      {isOpenMobile && (
        <div className="fixed inset-0 z-50 lg:hidden flex flex-col justify-end bg-black/50 backdrop-blur-sm">
          <div className="bg-surface border-t border-line rounded-t-2xl p-5 max-h-[80vh] overflow-hidden shadow-lg animate-in slide-in-from-bottom duration-200">
            {content}
          </div>
        </div>
      )}
    </>
  );
}
