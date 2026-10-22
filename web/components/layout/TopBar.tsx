"use client";

import React from "react";
import Link from "next/link";
import { Info, Activity, Menu, History } from "lucide-react";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

interface TopBarProps {
  mode?: string;
  onToggleHistory?: () => void;
  onOpenMobileSources?: () => void;
  hasCitations?: boolean;
}

export function TopBar({
  mode = "Full",
  onToggleHistory,
  onOpenMobileSources,
  hasCitations,
}: TopBarProps) {
  const modeBadgeColor =
    mode.toLowerCase() === "rules"
      ? "text-warning bg-warning/10 border-warning/30"
      : mode.toLowerCase() === "limited"
      ? "text-muted bg-surface-2 border-line"
      : "text-accent-text bg-accent/10 border-accent/30";

  return (
    <header className="sticky top-0 z-40 w-full glass-surface border-b border-line/70">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        {/* Left: History drawer trigger & Wordmark */}
        <div className="flex items-center space-x-3">
          {onToggleHistory && (
            <button
              onClick={onToggleHistory}
              aria-label="Toggle history drawer"
              className="p-1.5 rounded-lg border border-line hover:bg-surface-2 text-muted hover:text-ink transition-colors"
              title="Recent Conversations"
            >
              <History className="w-4 h-4" />
            </button>
          )}

          <Link href="/" className="flex items-center space-x-2 group">
            {/* Abstract mark: stacked ledger lines forming a curve */}
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="text-accent group-hover:scale-105 transition-transform"
              aria-hidden="true"
            >
              <rect x="3" y="4" width="18" height="2" rx="1" fill="currentColor" opacity="0.4" />
              <rect x="5" y="9" width="16" height="2" rx="1" fill="currentColor" opacity="0.7" />
              <rect x="7" y="14" width="14" height="2" rx="1" fill="currentColor" />
              <rect x="11" y="19" width="10" height="2" rx="1" fill="currentColor" opacity="0.85" />
            </svg>
            <span className="font-serif font-bold text-lg tracking-tight text-ink">
              Regulator<span className="text-accent">IQ</span>
            </span>
          </Link>

          {/* Engine Mode Badge */}
          <span
            className={`hidden sm:inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold border ${modeBadgeColor}`}
          >
            {mode} Mode
          </span>
        </div>

        {/* Right: Sources (mobile), About, Status, Theme Toggle */}
        <div className="flex items-center space-x-2 sm:space-x-3">
          {hasCitations && onOpenMobileSources && (
            <button
              onClick={onOpenMobileSources}
              className="lg:hidden px-2.5 py-1 text-xs font-medium rounded-md border border-accent/40 bg-accent/10 text-accent-text"
            >
              Sources
            </button>
          )}

          <Link
            href="/about"
            className="p-2 rounded-lg text-muted hover:text-ink hover:bg-surface-2 transition-colors"
            title="About RegulatorIQ"
            aria-label="About page"
          >
            <Info className="w-4 h-4" />
          </Link>

          <Link
            href="/status"
            className="p-2 rounded-lg text-muted hover:text-ink hover:bg-surface-2 transition-colors"
            title="Service Status"
            aria-label="Service status"
          >
            <Activity className="w-4 h-4" />
          </Link>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
