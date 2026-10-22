/**
 * Pure runtime policy for selecting LiveBackground rendering tier.
 * Tiers: "webgl" | "canvas" | "static"
 */

export type BgTier = "webgl" | "canvas" | "static";

export interface SystemCapabilities {
  prefersReducedMotion?: boolean;
  reduceMotionOverride?: boolean;
  saveData?: boolean;
  deviceMemory?: number;
  hardwareConcurrency?: number;
  hasWebGL?: boolean;
  hasCanvas?: boolean;
  sessionTierOverride?: BgTier;
}

export function determineTier(caps: SystemCapabilities): BgTier {
  // Session override (e.g. from performance governor downgrade)
  if (caps.sessionTierOverride) {
    return caps.sessionTierOverride;
  }

  // 1. Static tier conditions: reduced motion, data saver, constrained hardware
  if (
    caps.prefersReducedMotion ||
    caps.reduceMotionOverride ||
    caps.saveData ||
    (caps.deviceMemory !== undefined && caps.deviceMemory <= 2) ||
    (caps.hardwareConcurrency !== undefined && caps.hardwareConcurrency <= 2)
  ) {
    return "static";
  }

  // 2. Hardware / API support checks
  if (caps.hasWebGL) {
    return "webgl";
  }

  if (caps.hasCanvas) {
    return "canvas";
  }

  return "static";
}

export function detectEnvironmentCapabilities(): SystemCapabilities {
  if (typeof window === "undefined") {
    return { hasWebGL: false, hasCanvas: false, prefersReducedMotion: true };
  }

  const nav = navigator as any;
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const saveData = Boolean(nav.connection?.saveData);
  const deviceMemory = typeof nav.deviceMemory === "number" ? nav.deviceMemory : undefined;
  const hardwareConcurrency = typeof nav.hardwareConcurrency === "number" ? nav.hardwareConcurrency : undefined;

  let sessionOverride: BgTier | undefined;
  try {
    const saved = sessionStorage.getItem("regulatoriq_bg_tier");
    if (saved === "static" || saved === "canvas" || saved === "webgl") {
      sessionOverride = saved;
    }
  } catch {
    // sessionStorage not available
  }

  // Check Canvas support
  let hasCanvas = false;
  try {
    const c = document.createElement("canvas");
    hasCanvas = Boolean(c.getContext("2d"));
  } catch {
    hasCanvas = false;
  }

  // Check WebGL support
  let hasWebGL = false;
  try {
    const c = document.createElement("canvas");
    hasWebGL = Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    hasWebGL = false;
  }

  return {
    prefersReducedMotion: prefersReduced,
    saveData,
    deviceMemory,
    hardwareConcurrency,
    hasWebGL,
    hasCanvas,
    sessionTierOverride: sessionOverride,
  };
}
