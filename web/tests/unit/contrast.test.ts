import { describe, it, expect } from "vitest";
import { checkAllContrasts } from "../../../scripts/check_contrast";

describe("Contrast and WCAG 2.2 AA Compliance", () => {
  it("enforces that all token pairs in both themes meet or exceed WCAG AA requirements", () => {
    const { results, allPassed } = checkAllContrasts();
    const failingPairs = results.filter((r) => !r.passed);

    if (failingPairs.length > 0) {
      console.error("Failing contrast pairs:", failingPairs);
    }

    expect(allPassed).toBe(true);
    expect(failingPairs.length).toBe(0);
  });
});
