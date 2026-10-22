"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Footer } from "@/components/layout/Footer";
import { defaultApiClient, ReadyResponse, MetaResponse } from "@/lib/apiClient";

interface ServerStatus {
  url: string;
  isHealthy: boolean;
  readyStatus?: string;
  mode?: string;
  indexVersion?: string;
  latencyMs: number;
  lastChecked: number;
}

export default function StatusPage() {
  const [statuses, setStatuses] = useState<ServerStatus[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchStatuses = async () => {
    setLoading(true);
    const urls = defaultApiClient.getUrls();
    const results: ServerStatus[] = [];

    for (const u of urls) {
      const start = performance.now();
      let healthy = false;
      let ready: ReadyResponse | undefined;
      let meta: MetaResponse | undefined;

      try {
        healthy = await defaultApiClient.checkHealth(u);
        if (healthy) {
          ready = await defaultApiClient.getReady(u).catch(() => undefined);
          meta = await defaultApiClient.getMeta(u).catch(() => undefined);
        }
      } catch {}

      const latency = Math.round(performance.now() - start);
      results.push({
        url: u,
        isHealthy: healthy,
        readyStatus: ready?.status || (healthy ? "healthy" : "offline"),
        mode: ready?.mode || meta?.mode || "Unknown",
        indexVersion: meta?.index_version || "N/A",
        latencyMs: latency,
        lastChecked: Date.now(),
      });
    }

    setStatuses(results);
    setLoading(false);
  };

  useEffect(() => {
    fetchStatuses();
    const interval = setInterval(fetchStatuses, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <TopBar />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Link
              href="/"
              className="inline-flex items-center space-x-1.5 text-xs text-muted hover:text-ink font-medium mb-2"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Regulatory Search</span>
            </Link>
            <h1 className="font-serif text-3xl font-bold text-ink tracking-tight">
              System & API Health
            </h1>
          </div>

          <button
            onClick={fetchStatuses}
            disabled={loading}
            className="p-2 rounded-lg border border-line hover:bg-surface-2 text-ink text-xs font-medium inline-flex items-center space-x-1.5 transition-colors disabled:opacity-50"
            aria-label="Refresh status"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>

        <div className="rounded-2xl border border-line bg-surface overflow-hidden shadow-xs">
          <table className="w-full text-left text-xs sm:text-sm">
            <thead className="bg-surface-2 border-b border-line text-muted font-medium">
              <tr>
                <th className="py-3 px-4">Endpoint</th>
                <th className="py-3 px-4">Liveness</th>
                <th className="py-3 px-4">Readiness State</th>
                <th className="py-3 px-4">Engine Mode</th>
                <th className="py-3 px-4">Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {statuses.map((s, idx) => (
                <tr key={idx} className="hover:bg-surface-2/40 transition-colors">
                  <td className="py-3.5 px-4 font-mono font-medium text-ink">
                    {s.url}
                  </td>
                  <td className="py-3.5 px-4">
                    {s.isHealthy ? (
                      <span className="inline-flex items-center space-x-1.5 text-success font-semibold">
                        <CheckCircle2 className="w-4 h-4" />
                        <span>Online</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1.5 text-danger font-semibold">
                        <AlertCircle className="w-4 h-4" />
                        <span>Unreachable</span>
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 capitalize font-mono text-muted">
                    {s.readyStatus}
                  </td>
                  <td className="py-3.5 px-4 font-medium text-ink">
                    {s.mode}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-muted">
                    {s.latencyMs} ms
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="p-4 rounded-xl border border-line bg-surface-2/30 flex items-center justify-between text-xs text-muted">
          <span>Auto-refreshes every 15 seconds.</span>
          <span className="font-mono">All probes compliant with CORS and security policies.</span>
        </div>
      </main>

      <Footer />
    </div>
  );
}
