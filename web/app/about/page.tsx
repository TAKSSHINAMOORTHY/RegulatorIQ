"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle, Database, ShieldCheck, GitFork, Cpu, ExternalLink } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Footer } from "@/components/layout/Footer";
import { defaultApiClient, MetaResponse } from "@/lib/apiClient";

export default function AboutPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);

  useEffect(() => {
    defaultApiClient.getMeta().then(setMeta).catch(() => {});
  }, []);

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <TopBar />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-8 space-y-10">
        <div>
          <Link
            href="/"
            className="inline-flex items-center space-x-1.5 text-xs text-muted hover:text-ink font-medium mb-4"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Regulatory Search</span>
          </Link>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-ink tracking-tight">
            About RegulatorIQ
          </h1>
          <p className="mt-2 text-sm sm:text-base text-muted leading-relaxed">
            An open-source, evidence-grounded regulatory intelligence engine built on the published corpus of the Reserve Bank of India.
          </p>
        </div>

        {/* 5-Step Architecture Diagram (Inline SVG) */}
        <section className="space-y-4">
          <h2 className="font-serif text-xl sm:text-2xl font-bold text-ink">
            How It Works: 5-Step Verifiable Pipeline
          </h2>

          <div className="p-6 rounded-2xl border border-line bg-surface shadow-xs">
            <svg
              viewBox="0 0 800 120"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="w-full h-auto text-ink"
              aria-label="5-step architecture diagram: Crawl official RBI -> Chunk & Link -> Hybrid Index -> Graph Resolution -> Grounded Generation"
            >
              {/* Step 1 */}
              <rect x="10" y="20" width="130" height="80" rx="10" className="fill-surface-2 stroke-line" strokeWidth="1.5" />
              <text x="75" y="55" textAnchor="middle" className="text-xs font-sans font-bold fill-ink">1. Acquisition</text>
              <text x="75" y="75" textAnchor="middle" className="text-[10px] font-sans fill-muted">RBI gazetted PDFs</text>

              {/* Arrow 1 */}
              <path d="M 145 60 L 175 60" className="stroke-accent" strokeWidth="2" markerEnd="url(#arrow)" />

              {/* Step 2 */}
              <rect x="180" y="20" width="130" height="80" rx="10" className="fill-surface-2 stroke-line" strokeWidth="1.5" />
              <text x="245" y="55" textAnchor="middle" className="text-xs font-sans font-bold fill-ink">2. Extraction</text>
              <text x="245" y="75" textAnchor="middle" className="text-[10px] font-sans fill-muted">Structural chunks</text>

              {/* Arrow 2 */}
              <path d="M 315 60 L 345 60" className="stroke-accent" strokeWidth="2" markerEnd="url(#arrow)" />

              {/* Step 3 */}
              <rect x="350" y="20" width="130" height="80" rx="10" className="fill-surface-2 stroke-line" strokeWidth="1.5" />
              <text x="415" y="55" textAnchor="middle" className="text-xs font-sans font-bold fill-ink">3. Hybrid Search</text>
              <text x="415" y="75" textAnchor="middle" className="text-[10px] font-sans fill-muted">BM25 + Vector + Rerank</text>

              {/* Arrow 3 */}
              <path d="M 485 60 L 515 60" className="stroke-accent" strokeWidth="2" markerEnd="url(#arrow)" />

              {/* Step 4 */}
              <rect x="520" y="20" width="130" height="80" rx="10" className="fill-surface-2 stroke-line" strokeWidth="1.5" />
              <text x="585" y="55" textAnchor="middle" className="text-xs font-sans font-bold fill-ink">4. Validity Graph</text>
              <text x="585" y="75" textAnchor="middle" className="text-[10px] font-sans fill-muted">Supersession resolution</text>

              {/* Arrow 4 */}
              <path d="M 655 60 L 685 60" className="stroke-accent" strokeWidth="2" markerEnd="url(#arrow)" />

              {/* Step 5 */}
              <rect x="690" y="20" width="100" height="80" rx="10" className="fill-accent/10 stroke-accent" strokeWidth="1.5" />
              <text x="740" y="55" textAnchor="middle" className="text-xs font-sans font-bold fill-accent-text">5. Synthesis</text>
              <text x="740" y="75" textAnchor="middle" className="text-[10px] font-sans fill-muted">Grounded facts</text>
            </svg>
          </div>
        </section>

        {/* Live Corpus Statistics */}
        <section className="space-y-4">
          <h2 className="font-serif text-xl sm:text-2xl font-bold text-ink">
            Corpus Metadata & Coverage
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl border border-line bg-surface">
              <span className="text-xs text-muted font-medium">Index Version</span>
              <p className="font-mono text-lg font-bold text-ink mt-1">
                {meta?.index_version || "2024.10.1"}
              </p>
            </div>
            <div className="p-4 rounded-xl border border-line bg-surface">
              <span className="text-xs text-muted font-medium">Corpus Size</span>
              <p className="font-mono text-lg font-bold text-ink mt-1">
                {meta?.corpus?.documents ? `${meta.corpus.documents} documents` : "Indexed Official RBI"}
              </p>
            </div>
            <div className="p-4 rounded-xl border border-line bg-surface">
              <span className="text-xs text-muted font-medium">Active Engine Mode</span>
              <p className="font-mono text-lg font-bold text-accent-text mt-1">
                {meta?.mode || "Full Agentic RAG"}
              </p>
            </div>
          </div>
        </section>

        {/* Limitations & Legal Disclaimer */}
        <section className="p-5 rounded-2xl border border-warning/30 bg-warning/5 space-y-3">
          <h3 className="font-serif font-bold text-base text-warning">
            Crucial Limitations & Disclaimer
          </h3>
          <p className="text-xs sm:text-sm text-ink leading-relaxed">
            RegulatorIQ is an independent technical demonstration. It does not replace the counsel of qualified banking compliance attorneys. While every citation links directly to authoritative publications, administrative circulars may be subject to internal directives or unindexed bilateral notifications.
          </p>
          <div className="pt-2">
            <a
              href="https://www.rbi.org.in"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center space-x-1 text-xs text-accent-text hover:text-accent font-semibold hover:underline"
            >
              <span>Visit Official Reserve Bank of India Portal</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
