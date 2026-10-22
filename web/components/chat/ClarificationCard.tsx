"use client";

import React from "react";
import { HelpCircle } from "lucide-react";

interface ClarificationCardProps {
  question: string;
  options: string[];
  onSelectOption: (option: string) => void;
}

export function ClarificationCard({
  question,
  options,
  onSelectOption,
}: ClarificationCardProps) {
  return (
    <div className="p-4 rounded-xl border border-accent/40 bg-accent/5 text-ink space-y-3">
      <div className="flex items-start space-x-3">
        <HelpCircle className="w-5 h-5 text-accent shrink-0 mt-0.5" />
        <div>
          <h4 className="font-semibold text-accent-text text-sm sm:text-base">
            Clarification Needed
          </h4>
          <p className="mt-1 text-xs sm:text-sm text-ink leading-relaxed font-medium">
            {question}
          </p>
        </div>
      </div>

      {options && options.length > 0 && (
        <div className="pt-2 flex flex-wrap gap-2">
          {options.map((opt, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectOption(opt)}
              className="px-3 py-1.5 rounded-lg border border-accent/30 bg-surface hover:bg-accent hover:text-white text-xs sm:text-sm font-medium transition-colors shadow-sm"
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
