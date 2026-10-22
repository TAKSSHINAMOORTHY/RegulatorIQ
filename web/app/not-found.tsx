import React from "react";
import Link from "next/link";
import { ArrowLeft, FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center space-y-4">
      <div className="w-16 h-16 rounded-2xl bg-surface-2 border border-line flex items-center justify-center text-accent">
        <FileQuestion className="w-8 h-8" />
      </div>
      <h1 className="font-serif text-3xl sm:text-4xl font-bold text-ink">
        404 - Document Not Located
      </h1>
      <p className="text-sm text-muted max-w-md">
        The regulatory section or route you were seeking does not exist in the RegulatorIQ portal index.
      </p>
      <Link
        href="/"
        className="px-4 py-2 rounded-xl bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors inline-flex items-center space-x-2"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Return to Regulatory Assistant</span>
      </Link>
    </div>
  );
}
