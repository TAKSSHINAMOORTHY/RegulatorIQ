import { describe, it, expect } from "vitest";
import { determineTier, detectEnvironmentCapabilities } from "@/components/background/policy";

describe("LiveBackground Tier Policy", () => {
  it("selects static tier when prefersReducedMotion is true", () => {
    const tier = determineTier({
      prefersReducedMotion: true,
      hasWebGL: true,
      hasCanvas: true,
    });
    expect(tier).toBe("static");
  });

  it("selects static tier when user reduceMotionOverride is true", () => {
    const tier = determineTier({
      reduceMotionOverride: true,
      hasWebGL: true,
      hasCanvas: true,
    });
    expect(tier).toBe("static");
  });

  it("selects static tier when saveData is enabled", () => {
    const tier = determineTier({
      saveData: true,
      hasWebGL: true,
    });
    expect(tier).toBe("static");
  });

  it("selects static tier for low-power hardware (deviceMemory <= 2)", () => {
    const tier = determineTier({
      deviceMemory: 2,
      hardwareConcurrency: 4,
      hasWebGL: true,
    });
    expect(tier).toBe("static");
  });

  it("selects canvas tier when WebGL is unavailable but canvas is supported", () => {
    const tier = determineTier({
      hasWebGL: false,
      hasCanvas: true,
    });
    expect(tier).toBe("canvas");
  });

  it("selects webgl tier when GPU and capability requirements are met", () => {
    const tier = determineTier({
      hasWebGL: true,
      hasCanvas: true,
      deviceMemory: 8,
      hardwareConcurrency: 8,
    });
    expect(tier).toBe("webgl");
  });

  it("detects environment capabilities in browser environment", () => {
    const caps = detectEnvironmentCapabilities();
    expect(typeof caps.hasCanvas).toBe("boolean");
    expect(typeof caps.hasWebGL).toBe("boolean");
  });
});
