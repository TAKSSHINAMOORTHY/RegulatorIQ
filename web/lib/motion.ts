/**
 * Unified motion preference hook and transition presets.
 * Adheres strictly to WCAG 2.2 AA reduced motion requirements and motion budget.
 */

import { useState, useEffect } from "react";
import { loadPreferences } from "./storage";

export function useMotionPreference(): { prefersReducedMotion: boolean } {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const checkMotion = () => {
      const prefs = loadPreferences();
      setReduced(mediaQuery.matches || prefs.reduceMotionOverride);
    };

    checkMotion();
    mediaQuery.addEventListener("change", checkMotion);
    window.addEventListener("storage", checkMotion);

    return () => {
      mediaQuery.removeEventListener("change", checkMotion);
      window.removeEventListener("storage", checkMotion);
    };
  }, []);

  return { prefersReducedMotion: reduced };
}

export const springPresets = {
  messageEnter: {
    type: "spring",
    stiffness: 400,
    damping: 30,
    mass: 0.8,
  },
  cardHover: {
    type: "spring",
    stiffness: 300,
    damping: 20,
  },
  stampInkIn: {
    type: "spring",
    stiffness: 500,
    damping: 25,
  },
};

export const transitionFallback = {
  duration: 0.18,
  ease: "easeOut",
};
