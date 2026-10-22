import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useMotionPreference, springPresets, transitionFallback } from "@/lib/motion";

describe("Motion Utilities", () => {
  it("provides valid spring and transition presets", () => {
    expect(springPresets.messageEnter.type).toBe("spring");
    expect(springPresets.messageEnter.stiffness).toBeGreaterThan(0);
    expect(transitionFallback.duration).toBeGreaterThan(0);
  });

  it("reads motion preference hook", () => {
    const { result } = renderHook(() => useMotionPreference());
    expect(typeof result.current.prefersReducedMotion).toBe("boolean");
  });
});
