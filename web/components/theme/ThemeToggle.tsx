"use client";

import React, { useState, useEffect } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon, Laptop } from "lucide-react";
import { savePreferences } from "@/lib/storage";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const cycleTheme = (event: React.MouseEvent<HTMLButtonElement>) => {
    const nextTheme = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";

    // View Transitions API circular reveal if available
    const doc = document as any;
    if (doc.startViewTransition && event.clientX && event.clientY) {
      const x = event.clientX;
      const y = event.clientY;
      const endRadius = Math.hypot(
        Math.max(x, window.innerWidth - x),
        Math.max(y, window.innerHeight - y)
      );

      const transition = doc.startViewTransition(() => {
        setTheme(nextTheme);
        savePreferences({ theme: nextTheme as any });
      });

      transition.ready.then(() => {
        doc.documentElement.animate(
          {
            clipPath: [
              `circle(0px at ${x}px ${y}px)`,
              `circle(${endRadius}px at ${x}px ${y}px)`,
            ],
          },
          {
            duration: 350,
            easing: "ease-in-out",
            pseudoElement: "::view-transition-new(root)",
          }
        );
      });
    } else {
      setTheme(nextTheme);
      savePreferences({ theme: nextTheme as any });
    }
  };

  if (!mounted) {
    return (
      <button
        aria-label="Toggle theme"
        className="w-9 h-9 rounded-md border border-line flex items-center justify-center text-muted"
      >
        <span className="w-4 h-4" />
      </button>
    );
  }

  const label =
    theme === "system"
      ? `System (${resolvedTheme})`
      : theme === "dark"
      ? "Dark theme"
      : "Light theme";

  return (
    <button
      onClick={cycleTheme}
      aria-label={`Current theme: ${label}. Click to cycle.`}
      title={`Theme: ${label}`}
      className="relative w-9 h-9 rounded-md border border-line hover:border-accent flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
    >
      {theme === "system" ? (
        <Laptop className="w-4 h-4 text-muted hover:text-ink transition-colors" />
      ) : resolvedTheme === "dark" ? (
        <Moon className="w-4 h-4 text-accent hover:text-ink transition-transform duration-200 rotate-0" />
      ) : (
        <Sun className="w-4 h-4 text-accent hover:text-ink transition-transform duration-200 rotate-0" />
      )}
      <span className="sr-only">Toggle theme</span>
    </button>
  );
}
