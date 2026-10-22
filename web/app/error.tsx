"use client";

import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("UI Uncaught Error Boundary:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center space-y-4">
      <div className="w-16 h-16 rounded-2xl bg-danger/10 border border-danger/30 flex items-center justify-center text-danger">
        <AlertTriangle className="w-8 h-8" />
      </div>
      <h1 className="font-serif text-3xl font-bold text-ink">
        An Interface Error Occurred
      </h1>
      <p className="text-sm text-muted max-w-md">
        {error.message || "An unexpected error disrupted the interface rendering."}
      </p>
      <button
        onClick={() => reset()}
        className="px-4 py-2 rounded-xl bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors inline-flex items-center space-x-2"
      >
        <RefreshCw className="w-4 h-4" />
        <span>Reload Interface</span>
      </button>
    </div>
  );
}
