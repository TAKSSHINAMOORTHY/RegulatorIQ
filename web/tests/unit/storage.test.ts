import { describe, it, expect, beforeEach } from "vitest";
import {
  loadPreferences,
  savePreferences,
  loadHistory,
  saveConversation,
  clearHistory,
} from "@/lib/storage";

describe("Storage Manager", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("loads and saves preferences correctly", () => {
    const defaultPrefs = loadPreferences();
    expect(defaultPrefs.theme).toBe("system");

    savePreferences({ theme: "dark", reduceMotionOverride: true });
    const updated = loadPreferences();
    expect(updated.theme).toBe("dark");
    expect(updated.reduceMotionOverride).toBe(true);
  });

  it("stores up to 30 conversations and clears them on demand", () => {
    for (let i = 1; i <= 35; i++) {
      saveConversation({
        id: `conv_${i}`,
        timestamp: Date.now() + i,
        question: `Question ${i}`,
        summary: `Answer ${i}`,
      });
    }

    const history = loadHistory();
    expect(history.length).toBe(30);
    // Most recent first
    expect(history[0].id).toBe("conv_35");

    clearHistory();
    expect(loadHistory().length).toBe(0);
  });

  it("respects opt-out preference", () => {
    savePreferences({ historyOptOut: true });
    saveConversation({
      id: "conv_optout",
      timestamp: Date.now(),
      question: "Private question",
      summary: "Private answer",
    });

    expect(loadHistory().length).toBe(0);
  });
});
