"use client";

import React from "react";
import { Sparkles, ArrowRight } from "lucide-react";

interface EmptyStateProps {
  onSelectPrompt: (promptText: string) => void;
}

const EXAMPLE_QUESTIONS = [
  {
    category: "Exact Lookup",
    query: "What is the capital adequacy ratio requirement for commercial banks?",
  },
  {
    category: "Validity & Supersession",
    query: "Is circular DBOD.No.BP.BC.9/21.04.048/2014-15 on liquidity coverage ratio still in force?",
  },
  {
    category: "Regulatory Comparison",
    query: "Compare prudential norms on income recognition between commercial banks and NBFCs",
  },
  {
    category: "Quantitative Threshold",
    query: "What are the single and group exposure limits for large exposures framework (LEF)?",
  },
  {
    category: "Statutory Definition",
    query: "How is 'Systemically Important Non-Deposit Taking NBFC' defined under RBI Master Directions?",
  },
  {
    category: "Scope & Applicability",
    query: "Do priority sector lending targets apply to foreign banks with less than 20 branches?",
  },
];

export function EmptyState({ onSelectPrompt }: EmptyStateProps) {
  return (
    <div className="py-6 sm:py-10 space-y-8 text-center max-w-2xl mx-auto">
      <div className="space-y-3">
        <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-ink leading-tight">
          Regulatory Intelligence, <br />
          <span className="text-accent underline decoration-accent/30 underline-offset-8">
            Direct from the Source
          </span>
        </h1>
        <p className="text-sm sm:text-base text-muted max-w-lg mx-auto leading-relaxed">
          Ask precise compliance and regulatory questions against official Reserve Bank of India circulars, master directions, and notifications.
        </p>
      </div>

      {/* 6 Example Question Chips */}
      <div className="space-y-3 text-left">
        <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-muted">
          <Sparkles className="w-3.5 h-3.5 text-accent" />
          <span>Curated Questions to Try</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {EXAMPLE_QUESTIONS.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectPrompt(item.query)}
              className="p-3 rounded-xl border border-line bg-surface hover:border-accent hover:bg-surface-2/70 text-left transition-all group flex flex-col justify-between shadow-xs"
            >
              <div>
                <span className="text-[10px] font-mono font-semibold uppercase text-accent-text block mb-1">
                  {item.category}
                </span>
                <p className="text-xs sm:text-sm text-ink group-hover:text-accent-text font-medium leading-snug">
                  {item.query}
                </p>
              </div>
              <div className="mt-2 flex justify-end">
                <ArrowRight className="w-3.5 h-3.5 text-muted group-hover:text-accent group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Honest disclaimer line */}
      <div className="pt-2 border-t border-line/60">
        <p className="text-xs text-muted leading-relaxed">
          <strong>What this tool is not:</strong> Not legal counsel or automated binding advice. It is a verifiable synthesis engine grounded with exact citations and validity graph checks.
        </p>
      </div>
    </div>
  );
}
