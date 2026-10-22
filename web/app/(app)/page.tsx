"use client";

import React, { useReducer, useState, useRef, useEffect, useCallback } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Footer } from "@/components/layout/Footer";
import { HistoryDrawer } from "@/components/layout/HistoryDrawer";
import { EmptyState } from "@/components/chat/EmptyState";
import { Composer } from "@/components/chat/Composer";
import { MarkdownAnswer } from "@/components/chat/MarkdownAnswer";
import { AgentTimeline } from "@/components/chat/AgentTimeline";
import { SourcesPanel } from "@/components/citations/SourcesPanel";
import { RefusalCard } from "@/components/chat/RefusalCard";
import { ClarificationCard } from "@/components/chat/ClarificationCard";
import { WakingPanel } from "@/components/chat/WakingPanel";
import { FeedbackControl } from "@/components/chat/FeedbackControl";
import {
  conversationReducer,
  initialConversationState,
  ConversationState,
} from "@/lib/reducer";
import { defaultApiClient, ApiError } from "@/lib/apiClient";
import { saveConversation } from "@/lib/storage";
import { AlertTriangle, Clock } from "lucide-react";

export default function ChatPage() {
  const [state, dispatch] = useReducer(conversationReducer, initialConversationState);
  const [isWaking, setIsWaking] = useState(false);
  const [rateLimitTimer, setRateLimitTimer] = useState<number | null>(null);
  const [offlineError, setOfflineError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [mobileSourcesOpen, setMobileSourcesOpen] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Check initial engine readiness on load
  useEffect(() => {
    defaultApiClient
      .getReady()
      .then((ready) => {
        if (ready.status === "starting" || ready.status === "loading_models" || ready.status === "warming") {
          setIsWaking(true);
        }
      })
      .catch((err) => {
        if (err instanceof ApiError && err.kind === "waking_up") {
          setIsWaking(true);
        }
      });
  }, []);

  // Auto-scroll as tokens stream
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.messages, state.status]);

  // Rate-limit countdown timer
  useEffect(() => {
    if (rateLimitTimer === null || rateLimitTimer <= 0) return;
    const interval = setInterval(() => {
      setRateLimitTimer((prev) => (prev && prev > 1 ? prev - 1 : null));
    }, 1000);
    return () => clearInterval(interval);
  }, [rateLimitTimer]);

  const handleSend = useCallback(
    async (
      question: string,
      options?: { asOfDate?: string; includeSuperseded?: boolean }
    ) => {
      setOfflineError(null);
      dispatch({ type: "START_ASK", question });

      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;

      try {
        const stream = defaultApiClient.ask(
          {
            question,
            options: {
              as_of: options?.asOfDate ?? null,
              include_superseded: options?.includeSuperseded ?? false,
              interactive: true,
            },
          },
          signal
        );

        let finalAnswer = "";
        let requestId = "";

        for await (const event of stream) {
          dispatch({ type: "APPLY_EVENT", event });
          if (event.type === "token") {
            finalAnswer += String(event.data?.delta ?? event.data?.text ?? "");
          }
          if (event.type === "meta" && event.data?.request_id) {
            requestId = String(event.data.request_id);
          }
        }

        // Save conversation turn to local storage
        if (finalAnswer.trim()) {
          saveConversation({
            id: requestId || `conv_${Date.now()}`,
            timestamp: Date.now(),
            question,
            summary: finalAnswer.slice(0, 140) + "...",
          });
        }
      } catch (err: any) {
        if (signal.aborted) {
          dispatch({ type: "CANCEL" });
          return;
        }

        if (err instanceof ApiError) {
          if (err.kind === "waking_up") {
            setIsWaking(true);
          } else if (err.kind === "rate_limited") {
            setRateLimitTimer(err.retryAfterSeconds || 60);
          } else if (err.kind === "offline") {
            setOfflineError("Could not reach RegulatorIQ API hosts. The server may be offline.");
          }
        }

        dispatch({
          type: "APPLY_EVENT",
          event: {
            seq: 999,
            step: "error",
            type: "error",
            data: { error: err.message || "An unexpected error occurred." },
          },
        });
      } finally {
        abortControllerRef.current = null;
      }
    },
    []
  );

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      dispatch({ type: "CANCEL" });
    }
  };

  const handleCitationClick = (idx: number) => {
    setActiveCitation(idx);
    setMobileSourcesOpen(true);
    // Smooth scroll to card
    const elem = document.getElementById(`source-card-${idx}`);
    elem?.scrollIntoView({ behavior: "smooth", block: "center" });
    elem?.focus();
  };

  const activeMsg = state.messages[state.activeMessageIndex];
  const allCitations = activeMsg?.citations || [];
  const currentMode = activeMsg?.mode || "Full";
  const isStreaming = state.status === "streaming" || state.status === "searching" || state.status === "verifying";

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      <TopBar
        mode={currentMode}
        onToggleHistory={() => setHistoryOpen(true)}
        onOpenMobileSources={() => setMobileSourcesOpen(true)}
        hasCitations={allCitations.length > 0}
      />

      <HistoryDrawer
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onSelectConversation={(q) => handleSend(q)}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex gap-6">
        {/* Main Chat Column */}
        <div className="flex-1 max-w-chat mx-auto flex flex-col justify-between">
          <div className="space-y-6 flex-1">
            {state.messages.length === 0 ? (
              <EmptyState onSelectPrompt={(q) => handleSend(q)} />
            ) : (
              state.messages.map((msg) => {
                const isMsgDone = msg.status === "done";
                const hasSuperseded = msg.citations.some(
                  (c) => c.statusStamp === "SUPERSEDED"
                );

                return (
                  <div key={msg.id} className="space-y-4 animate-in fade-in duration-200">
                    {/* User Question Bubble */}
                    <div className="flex justify-end">
                      <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-tr-xs bg-surface-2 border border-line p-3.5 sm:p-4 text-ink text-sm sm:text-base font-medium shadow-xs">
                        {msg.question}
                      </div>
                    </div>

                    {/* Agent Answer Card */}
                    <div className="rounded-2xl border border-line bg-surface p-4 sm:p-6 shadow-sm space-y-4 relative">
                      {/* Timeline status steps */}
                      <AgentTimeline
                        timeline={msg.timeline}
                        isDone={isMsgDone || msg.status === "refused" || msg.status === "clarifying"}
                      />

                      {/* Streamed or rendered answer */}
                      {msg.answerText ? (
                        <div
                          aria-live="polite"
                          className="relative"
                        >
                          <MarkdownAnswer
                            content={msg.answerText}
                            onCitationClick={handleCitationClick}
                            activeCitation={activeCitation}
                          />
                          {/* Blinking ink caret while streaming */}
                          {msg.status === "streaming" && (
                            <span className="inline-block w-1.5 h-4 ml-1 bg-accent align-middle animate-pulse" />
                          )}
                        </div>
                      ) : null}

                      {/* Refusal Card */}
                      {msg.refusal && (
                        <RefusalCard
                          reason={msg.refusal.reason}
                          relatedDocs={msg.refusal.relatedDocs}
                        />
                      )}

                      {/* Clarification Card */}
                      {msg.clarification && (
                        <ClarificationCard
                          question={msg.clarification.question}
                          options={msg.clarification.options}
                          onSelectOption={(opt) => handleSend(`${msg.question} (${opt})`)}
                        />
                      )}

                      {/* Error state */}
                      {msg.error && (
                        <div className="p-3 rounded-lg border border-danger/30 bg-danger/5 text-danger text-xs sm:text-sm flex items-center space-x-2">
                          <AlertTriangle className="w-4 h-4 shrink-0" />
                          <span>{msg.error}</span>
                        </div>
                      )}

                      {/* Grounding summary badge */}
                      {msg.grounding && (
                        <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded bg-success/10 border border-success/30 text-success text-xs font-medium">
                          <span>
                            Verified: {msg.grounding.supportedClaims}/{msg.grounding.totalClaims} claims supported
                          </span>
                          <span className="text-muted text-[10px]">
                            ({msg.grounding.judge})
                          </span>
                        </div>
                      )}

                      {/* Actions: Copy, Feedback, Historical re-query */}
                      {isMsgDone && (
                        <FeedbackControl
                          requestId={msg.requestId}
                          answerText={msg.answerText}
                          citations={msg.citations}
                          hasSuperseded={hasSuperseded}
                          onAskHistorical={() =>
                            handleSend(msg.question, { includeSuperseded: true })
                          }
                        />
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {/* Cold start waking panel */}
            {isWaking && (
              <WakingPanel
                onReady={() => setIsWaking(false)}
                queuedQuestion={state.messages[state.messages.length - 1]?.question}
              />
            )}

            {/* Rate-limit card */}
            {rateLimitTimer !== null && (
              <div className="p-4 rounded-xl border border-warning/40 bg-warning/10 text-ink flex items-center space-x-3">
                <Clock className="w-5 h-5 text-warning shrink-0" />
                <div className="text-xs sm:text-sm">
                  <strong>Rate limit reached.</strong> Please wait{" "}
                  <span className="font-mono font-bold">{rateLimitTimer}s</span> before sending your next query.
                </div>
              </div>
            )}

            {/* Offline Error banner */}
            {offlineError && (
              <div className="p-4 rounded-xl border border-danger/40 bg-danger/10 text-danger text-xs sm:text-sm flex items-center justify-between">
                <span>{offlineError}</span>
                <button
                  onClick={() => handleSend(state.messages[state.messages.length - 1]?.question || "Test")}
                  className="px-2.5 py-1 rounded bg-danger text-white text-xs font-semibold hover:bg-danger/90"
                >
                  Retry
                </button>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Sticky Composer */}
          <div className="sticky bottom-0 pt-4 pb-2 bg-gradient-to-t from-bg via-bg/95 to-transparent">
            <Composer
              onSend={handleSend}
              onStop={handleStop}
              isStreaming={isStreaming}
              disabled={isWaking || rateLimitTimer !== null}
              disabledReason={
                isWaking
                  ? "Server is waking up..."
                  : rateLimitTimer !== null
                  ? `Rate limited (${rateLimitTimer}s remaining)`
                  : undefined
              }
            />
          </div>
        </div>

        {/* Right Sources Panel */}
        <SourcesPanel
          citations={allCitations}
          activeCitation={activeCitation}
          isOpenMobile={mobileSourcesOpen}
          onCloseMobile={() => setMobileSourcesOpen(false)}
        />
      </main>

      <Footer />
    </div>
  );
}
