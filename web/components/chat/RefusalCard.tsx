"use client";

import React from "react";
import { ShieldAlert, FileText } from "lucide-react";

interface RefusalCardProps {
  reason: string;
  relatedDocs?: string[];
}

export function RefusalCard({ reason, relatedDocs }: RefusalCardProps) {
  return (
    <div
      role="alert"
      className="p-4 rounded-xl border border-warning/40 bg-warning/5 text-ink space-y-3"
    >
      <div className="flex items-start space-x-3">
        <ShieldAlert className="w-5 h-5 text-warning shrink-0 mt-0.5" />
        <div>
          <h4 className="font-semibold text-warning text-sm sm:text-base">
            Request Declined by Policy Guard
          </h4>
          <p className="mt-1 text-xs sm:text-sm text-ink leading-relaxed">
            {reason}
          </p>
        </div>
      </div>

      {relatedDocs && relatedDocs.length > 0 && (
        <div className="pt-2 border-t border-warning/20">
          <p className="text-xs font-medium text-muted mb-1.5">
            Related Official Reference Documents:
          </p>
          <ul className="space-y-1">
            {relatedDocs.map((doc, idx) => (
              <li key={idx} className="flex items-center space-x-2 text-xs text-ink">
                <FileText className="w-3.5 h-3.5 text-accent" />
                <span>{doc}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
