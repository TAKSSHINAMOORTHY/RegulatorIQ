import { describe, it, expect } from "vitest";
import { isAllowedRbiUrl } from "@/components/citations/SourceCard";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MarkdownAnswer } from "@/components/chat/MarkdownAnswer";

describe("Security and Sanitization", () => {
  it("strictly validates rbi.org.in domain whitelist", () => {
    // Valid RBI hosts
    expect(isAllowedRbiUrl("https://rbi.org.in/scripts/BS_CircularIndexDisplay.aspx")).toBe(true);
    expect(isAllowedRbiUrl("https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=123")).toBe(true);
    expect(isAllowedRbiUrl("https://m.rbi.org.in/doc.pdf")).toBe(true);

    // Invalid / lookalike attack hosts
    expect(isAllowedRbiUrl("https://rbi.org.in.attacker.com/steal")).toBe(false);
    expect(isAllowedRbiUrl("https://fake-rbi.org.in/doc.pdf")).toBe(false);
    expect(isAllowedRbiUrl("https://google.com")).toBe(false);
    expect(isAllowedRbiUrl("javascript:alert(1)")).toBe(false);
    expect(isAllowedRbiUrl("")).toBe(false);
    expect(isAllowedRbiUrl(undefined)).toBe(false);
  });

  it("safely neutralizes HTML injection in markdown answers", () => {
    const malicious = '<script>alert("pwned")</script><b>Injected Bold</b>';
    const { container } = render(React.createElement(MarkdownAnswer, { content: malicious }));

    expect(container.querySelector("script")).toBeNull();
    // Raw tags sanitized, no raw HTML rendered
    expect(container.innerHTML).not.toContain("<script>");
  });
});
