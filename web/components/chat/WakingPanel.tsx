"use client";

import React, { useState, useEffect } from "react";
import { Server, RefreshCw } from "lucide-react";
import Link from "next/link";
import { defaultApiClient, ApiError } from "@/lib/apiClient";

interface WakingPanelProps {
  onReady: () => void;
  queuedQuestion?: string;
}

export function WakingPanel({ onReady, queuedQuestion }: WakingPanelProps) {
  const [elapsed, setElapsed] = useState(0);
  const [stage, setStage] = useState("Connecting to server...");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);

    let active = true;
    let delay = 2000;

    const poll = async () => {
      if (!active) return;
      try {
        const ready = await defaultApiClient.getReady();
        if (ready.status === "ready" || ready.status === "degraded") {
          onReady();
          return;
        }
      } catch (err: any) {
        if (err instanceof ApiError && err.stage) {
          setStage(`Loading ${err.stage}...`);
        }
      }

      if (elapsed > 90) {
        setFailed(true);
        return;
      }

      delay = Math.min(8000, delay * 1.5);
      setTimeout(poll, delay);
    };

    poll();

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [elapsed, onReady]);

  if (failed) {
    return (
      <div
        role="status"
        className="p-5 rounded-xl border border-danger/40 bg-danger/5 text-ink text-center space-y-3"
      >
        <Server className="w-8 h-8 mx-auto text-danger" />
        <h3 className="font-serif font-bold text-base sm:text-lg text-ink">
          Server Did Not Awaken
        </h3>
        <p className="text-xs sm:text-sm text-muted max-w-md mx-auto">
          The free-tier hosting instance took longer than 90 seconds to respond. You can check the live server health or try again.
        </p>
        <div className="flex items-center justify-center space-x-3 pt-2">
          <button
            onClick={() => {
              setFailed(false);
              setElapsed(0);
            }}
            className="px-4 py-2 rounded-lg bg-accent text-white font-medium text-xs sm:text-sm hover:bg-accent/90 transition-colors inline-flex items-center space-x-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Retry Connection</span>
          </button>
          <Link
            href="/status"
            className="px-4 py-2 rounded-lg border border-line bg-surface hover:bg-surface-2 text-xs sm:text-sm font-medium transition-colors"
          >
            Check Status Page
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div
      role="status"
      className="p-5 rounded-xl border border-accent/30 bg-surface-2/60 text-ink space-y-3 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <Server className="w-5 h-5 text-accent animate-pulse" />
          <h3 className="font-serif font-bold text-sm sm:text-base text-ink">
            Waking up the free server
          </h3>
        </div>
        <span className="font-mono text-xs text-muted tabular-nums">
          Elapsed: {elapsed}s
        </span>
      </div>

      <p className="text-xs sm:text-sm text-muted leading-relaxed">
        Free hosting sleeps when idle to preserve credits. Spinning up the ML model and indices typically takes 20 to 45 seconds.
      </p>

      {/* Animated ledger progress bar */}
      <div className="w-full h-2 rounded-full bg-surface overflow-hidden border border-line">
        <div
          className="h-full bg-gradient-to-r from-accent via-accent-2 to-accent animate-[pulse_1.5s_infinite]"
          style={{ width: `${Math.min(95, elapsed * 2.5)}%` }}
        />
      </div>

      <div className="flex items-center justify-between text-xs text-muted">
        <span className="font-medium text-ink">{stage}</span>
        {queuedQuestion && (
          <span className="italic text-accent-text">
            Your question is queued and will execute automatically.
          </span>
        )}
      </div>
    </div>
  );
}
