import React from "react";
import Link from "next/link";
import { ArrowLeft, Shield, Lock, EyeOff } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Footer } from "@/components/layout/Footer";

export default function PrivacyPage() {
  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <TopBar />

      <main className="flex-1 max-w-3xl w-full mx-auto px-4 sm:px-6 py-8 space-y-8">
        <div>
          <Link
            href="/"
            className="inline-flex items-center space-x-1.5 text-xs text-muted hover:text-ink font-medium mb-4"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Regulatory Search</span>
          </Link>
          <h1 className="font-serif text-3xl sm:text-4xl font-bold text-ink tracking-tight">
            Privacy & Data Sovereignty
          </h1>
          <p className="mt-2 text-sm sm:text-base text-muted leading-relaxed">
            RegulatorIQ is built with privacy-by-design principles: zero telemetry tracking, no persistent query logging on servers, and on-device conversation storage.
          </p>
        </div>

        <div className="space-y-6 text-sm text-ink leading-relaxed">
          <section className="p-5 rounded-2xl border border-line bg-surface space-y-2.5">
            <div className="flex items-center space-x-2 text-accent font-semibold text-base">
              <EyeOff className="w-5 h-5" />
              <h3>1. On-Device Conversation History</h3>
            </div>
            <p className="text-muted">
              Your search prompts, questions, and responses are kept strictly inside your browser&apos;s <code>localStorage</code>. They are never synchronized to our servers or cross-referenced across user sessions. You can wipe your local history at any time using the &ldquo;Clear history&rdquo; button in the drawer.
            </p>
          </section>

          <section className="p-5 rounded-2xl border border-line bg-surface space-y-2.5">
            <div className="flex items-center space-x-2 text-accent font-semibold text-base">
              <Shield className="w-5 h-5" />
              <h3>2. Server-Side PII Scrubbing</h3>
            </div>
            <p className="text-muted">
              When user feedback or operational traces are captured, automated sanitization algorithms scrub personal identifiers (such as phone numbers, email addresses, Permanent Account Numbers (PAN), and Aadhaar patterns) before appending data to audit logs.
            </p>
          </section>

          <section className="p-5 rounded-2xl border border-line bg-surface space-y-2.5">
            <div className="flex items-center space-x-2 text-accent font-semibold text-base">
              <Lock className="w-5 h-5" />
              <h3>3. No Third-Party Trackers or Fonts</h3>
            </div>
            <p className="text-muted">
              This application loads no analytics trackers, tracking pixels, or third-party ad networks. All typography assets (Inter, Fraunces, JetBrains Mono) are packaged and self-hosted at build time.
            </p>
          </section>
        </div>
      </main>

      <Footer />
    </div>
  );
}
