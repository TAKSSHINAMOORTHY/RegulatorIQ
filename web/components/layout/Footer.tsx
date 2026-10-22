"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { AlertCircle, X } from "lucide-react";

interface FooterProps {
  disclaimerText?: string;
}

const DEFAULT_DISCLAIMER =
  "RegulatorIQ is an unofficial research tool synthesizing published Reserve Bank of India documents. It is not affiliated with the RBI and does not constitute legal, financial, or regulatory compliance advice. Always verify with official gazetted notifications.";

export function Footer({ disclaimerText = DEFAULT_DISCLAIMER }: FooterProps) {
  const [showNotice, setShowNotice] = useState(false);

  useEffect(() => {
    try {
      const dismissed = localStorage.getItem("regulatoriq_first_visit_dismissed");
      if (!dismissed) {
        setShowNotice(true);
      }
    } catch {}
  }, []);

  const dismissNotice = () => {
    setShowNotice(false);
    try {
      localStorage.setItem("regulatoriq_first_visit_dismissed", "1");
    } catch {}
  };

  return (
    <footer className="w-full border-t border-line/60 bg-surface/80 text-xs text-muted py-3 px-4 sm:px-6">
      <div className="max-w-7xl mx-auto space-y-2">
        {/* Dismissible first-visit notice */}
        {showNotice && (
          <div className="p-3 rounded-lg border border-accent/30 bg-accent/5 text-ink flex items-start justify-between gap-2 animate-in fade-in duration-300">
            <div className="flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 text-accent shrink-0 mt-0.5" />
              <p className="text-xs leading-relaxed">
                <strong>Welcome to RegulatorIQ:</strong> An open research tool for exploring official RBI circulars, Master Directions, and regulatory notifications with provenance tracking and validity verification.
              </p>
            </div>
            <button
              onClick={dismissNotice}
              className="p-1 hover:text-ink text-muted shrink-0"
              aria-label="Dismiss notice"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Persistent slim disclaimer */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
          <p className="max-w-4xl text-[11px] leading-relaxed opacity-80">
            {disclaimerText}
          </p>
          <div className="flex items-center space-x-3 shrink-0 text-[11px]">
            <Link href="/about" className="hover:text-ink hover:underline">
              About & Methodology
            </Link>
            <span>•</span>
            <Link href="/privacy" className="hover:text-ink hover:underline">
              Privacy
            </Link>
            <span>•</span>
            <Link href="/status" className="hover:text-ink hover:underline">
              System Status
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
