"use client";

import React, { useEffect, useState } from "react";
import { History, Trash2, X, MessageSquare } from "lucide-react";
import { loadHistory, clearHistory, SavedConversation } from "@/lib/storage";

interface HistoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectConversation: (question: string) => void;
}

export function HistoryDrawer({
  isOpen,
  onClose,
  onSelectConversation,
}: HistoryDrawerProps) {
  const [history, setHistory] = useState<SavedConversation[]>([]);

  useEffect(() => {
    if (isOpen) {
      setHistory(loadHistory());
    }
  }, [isOpen]);

  const handleClear = () => {
    clearHistory();
    setHistory([]);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div className="relative w-80 max-w-[85vw] h-full bg-surface border-r border-line shadow-2xl flex flex-col z-10 animate-in slide-in-from-left duration-200">
        <div className="p-4 border-b border-line flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <History className="w-4 h-4 text-accent" />
            <h3 className="font-serif font-bold text-ink text-sm sm:text-base">
              Recent Conversations
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-muted hover:text-ink rounded"
            aria-label="Close history"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* History items list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {history.length === 0 ? (
            <div className="p-6 text-center text-muted text-xs">
              <MessageSquare className="w-6 h-6 mx-auto mb-2 opacity-30" />
              <p>No recent conversations saved on this device.</p>
              <p className="mt-1 opacity-75">
                Conversations are stored purely in local memory and never synced to our servers.
              </p>
            </div>
          ) : (
            history.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  onSelectConversation(item.question);
                  onClose();
                }}
                className="w-full text-left p-2.5 rounded-lg border border-transparent hover:border-line hover:bg-surface-2 transition-all group"
              >
                <p className="text-xs font-medium text-ink line-clamp-2 group-hover:text-accent-text">
                  {item.question}
                </p>
                <span className="text-[10px] text-muted font-mono mt-1 block">
                  {new Date(item.timestamp).toLocaleDateString()}
                </span>
              </button>
            ))
          )}
        </div>

        {/* Footer actions */}
        {history.length > 0 && (
          <div className="p-3 border-t border-line flex justify-end">
            <button
              onClick={handleClear}
              className="px-3 py-1.5 rounded text-xs text-danger hover:bg-danger/10 border border-transparent hover:border-danger/20 transition-colors inline-flex items-center space-x-1"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear history</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
