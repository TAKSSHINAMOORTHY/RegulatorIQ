import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Composer } from "@/components/chat/Composer";
import { AgentTimeline } from "@/components/chat/AgentTimeline";
import { SourceCard } from "@/components/citations/SourceCard";
import { RefusalCard } from "@/components/chat/RefusalCard";
import { ClarificationCard } from "@/components/chat/ClarificationCard";
import { WakingPanel } from "@/components/chat/WakingPanel";
import { FeedbackControl } from "@/components/chat/FeedbackControl";
import { EmptyState } from "@/components/chat/EmptyState";
import { SourcesPanel } from "@/components/citations/SourcesPanel";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { MarkdownAnswer } from "@/components/chat/MarkdownAnswer";
import type { TimelineStep } from "@/lib/reducer";

describe("Component Unit Tests", () => {
  it("renders EmptyState with 6 question chips and triggers onSelectPrompt", () => {
    const handleSelect = vi.fn();
    render(<EmptyState onSelectPrompt={handleSelect} />);

    expect(screen.getByText(/Regulatory Intelligence/i)).toBeInTheDocument();
    const chips = screen.getAllByRole("button");
    expect(chips.length).toBeGreaterThanOrEqual(6);

    fireEvent.click(chips[0]);
    expect(handleSelect).toHaveBeenCalled();
  });

  it("renders Composer, types text, and sends message", () => {
    const handleSend = vi.fn();
    render(<Composer onSend={handleSend} />);

    const textarea = screen.getByPlaceholderText(/Ask a regulatory question/i);
    fireEvent.change(textarea, { target: { value: "What is CRR?" } });
    expect(textarea).toHaveValue("What is CRR?");

    const sendBtn = screen.getByTitle(/Send \(Enter\)/i);
    fireEvent.click(sendBtn);
    expect(handleSend).toHaveBeenCalledWith("What is CRR?", {
      asOfDate: undefined,
      includeSuperseded: false,
    });
  });

  it("renders AgentTimeline with running and completed steps", () => {
    const steps: TimelineStep[] = [
      { id: "1", label: "Searching documents", status: "completed" },
      { id: "2", label: "Checking validity", status: "running" },
    ];
    render(<AgentTimeline timeline={steps} isDone={false} />);

    expect(screen.getByText(/Searching documents/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Checking validity/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders SourceCard with status stamp and circular number copy button", async () => {
    const citation = {
      id: "1",
      index: 1,
      title: "Master Direction on Exposure Norms",
      circularNumber: "RBI/2022-23/01",
      statusStamp: "CURRENT" as const,
      excerpt: "Exposure ceiling for single counterparties.",
      url: "https://www.rbi.org.in/notification.pdf",
    };

    render(<SourceCard citation={citation} isActive={true} />);

    expect(screen.getByText(/Master Direction on Exposure Norms/i)).toBeInTheDocument();
    expect(screen.getByText("CURRENT")).toBeInTheDocument();
    expect(screen.getByText("RBI/2022-23/01")).toBeInTheDocument();
    expect(screen.getByText(/Open on rbi.org.in/i)).toBeInTheDocument();
  });

  it("renders RefusalCard with security policy message", () => {
    render(
      <RefusalCard
        reason="Query asks for speculative predictions"
        relatedDocs={["FEMA 1999"]}
      />
    );

    expect(screen.getByText(/Request Declined by Policy Guard/i)).toBeInTheDocument();
    expect(screen.getByText(/speculative predictions/i)).toBeInTheDocument();
    expect(screen.getByText("FEMA 1999")).toBeInTheDocument();
  });

  it("renders ClarificationCard and responds to option buttons", () => {
    const handleOption = vi.fn();
    render(
      <ClarificationCard
        question="Which entity type are you interested in?"
        options={["NBFC", "Payment Bank"]}
        onSelectOption={handleOption}
      />
    );

    expect(screen.getByText(/Which entity type/i)).toBeInTheDocument();
    const btn = screen.getByText("NBFC");
    fireEvent.click(btn);
    expect(handleOption).toHaveBeenCalledWith("NBFC");
  });

  it("renders WakingPanel with progress description", () => {
    const handleReady = vi.fn();
    render(<WakingPanel onReady={handleReady} />);

    expect(screen.getByText(/Waking up the free server/i)).toBeInTheDocument();
    expect(screen.getByText(/Elapsed:/i)).toBeInTheDocument();
  });

  it("renders FeedbackControl and responds to upvote/downvote", () => {
    render(
      <FeedbackControl
        requestId="req_test_1"
        answerText="Sample verified answer text"
        citations={[]}
      />
    );

    expect(screen.getByTitle("Helpful")).toBeInTheDocument();
    expect(screen.getByTitle("Inaccurate or unhelpful")).toBeInTheDocument();

    const downBtn = screen.getByTitle("Inaccurate or unhelpful");
    fireEvent.click(downBtn);
    expect(screen.getByText("Outdated rule")).toBeInTheDocument();
  });

  it("renders SourcesPanel list", () => {
    const citations = [
      {
        id: "1",
        index: 1,
        title: "Circular A",
        statusStamp: "CURRENT" as const,
      },
      {
        id: "2",
        index: 2,
        title: "Circular B",
        statusStamp: "SUPERSEDED" as const,
      },
    ];
    render(<SourcesPanel citations={citations} activeCitation={1} />);

    expect(screen.getByText(/Official Sources \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText("Circular A")).toBeInTheDocument();
    expect(screen.getByText("Circular B")).toBeInTheDocument();
  });

  it("handles Composer paste, stop during streaming, and keyboard shortcuts", () => {
    const handleSend = vi.fn();
    const handleStop = vi.fn();
    const { rerender } = render(
      <Composer onSend={handleSend} onStop={handleStop} isStreaming={true} />
    );

    // Stop button
    const stopBtn = screen.getByLabelText(/Stop generating answer/i);
    expect(stopBtn).toBeInTheDocument();
    fireEvent.click(stopBtn);
    expect(handleStop).toHaveBeenCalled();

    // Rerender non-streaming
    rerender(<Composer onSend={handleSend} onStop={handleStop} isStreaming={false} />);
    const textarea = screen.getByPlaceholderText(/Ask a regulatory question/i);

    // Paste event
    fireEvent.paste(textarea, {
      clipboardData: {
        getData: () => "Short pasted text",
      },
    });
    expect(textarea).toHaveValue("Short pasted text");

    // Enter without shift sends
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(handleSend).toHaveBeenCalledWith("Short pasted text", {
      asOfDate: undefined,
      includeSuperseded: false,
    });
  });

  it("handles SourceCard expand and collapse for long excerpts", () => {
    const longCitation = {
      id: "2",
      index: 2,
      title: "Circular with long excerpt",
      statusStamp: "AS AMENDED" as const,
      supersededBy: "Master Circular 2024",
      amendedBy: "Amendment 2023",
      excerpt:
        "This is an extraordinarily long regulatory excerpt that exceeds one hundred and twenty characters in length to test the truncation toggle and expand/collapse interactive functionality cleanly.",
    };

    render(<SourceCard citation={longCitation} />);
    expect(screen.getByText(/Show more/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Show more/i));
    expect(screen.getByText(/Show less/i)).toBeInTheDocument();
  });
});
