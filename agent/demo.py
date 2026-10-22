"""CLI demo tool for RegulatorIQ Agentic RAG.

Usage:
    python -m agent.demo --question "What is the CRR requirement?"
"""

from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent.runner import AgentRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="RegulatorIQ Agent CLI Demo with Event Streaming")
    parser.add_argument("--question", "-q", type=str, required=True, help="Regulatory query to run")
    parser.add_argument("--as-of", type=str, default=None, help="Optional historical date (YYYY-MM-DD)")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive mode for clarifications")
    args = parser.parse_args()

    console = Console()
    console.print(Panel(f"[bold cyan]Query:[/bold cyan] {args.question}", title="RegulatorIQ Agent Demo"))

    runner = AgentRunner.from_config()
    opts = {}
    if args.as_of:
        opts["as_of"] = args.as_of
    if args.interactive:
        opts["interactive"] = True

    events_table = Table(title="Live Event Stream")
    events_table.add_column("Type", style="bold magenta", width=12)
    events_table.add_column("Details", style="green")

    final_answer = None

    for ev in runner.stream(args.question, session_opts=opts):
        ev_type = ev.get("type", "unknown")
        if ev_type == "final":
            final_answer = ev.get("answer")
            events_table.add_row(ev_type, f"Refused: {ev.get('refused')} | Citations: {len(ev.get('citations', []))}")
        elif ev_type == "plan":
            events_table.add_row(ev_type, f"Strategy: {ev.get('strategy')} | Sub-questions: {len(ev.get('sub_questions', []))}")
        elif ev_type == "retrieval":
            events_table.add_row(ev_type, f"Round {ev.get('round')} | Chunk counts: {ev.get('chunk_counts')}")
        elif ev_type == "grade":
            events_table.add_row(ev_type, f"Round {ev.get('round')} | Summary: {ev.get('grades_summary')}")
        elif ev_type == "validity":
            events_table.add_row(ev_type, f"Findings: {len(ev.get('findings', []))}")
        elif ev_type == "xref":
            events_table.add_row(ev_type, f"Cross-references: {len(ev.get('findings', []))}")
        elif ev_type == "grounding":
            events_table.add_row(ev_type, f"Passed: {ev.get('passed')} | Ratio: {ev.get('supported_ratio')}")
        elif ev_type == "token":
            # Don't clutter table with every token
            pass
        else:
            events_table.add_row(ev_type, json.dumps({k: v for k, v in ev.items() if k not in ("type", "timestamp")}))

    console.print(events_table)

    if final_answer:
        console.print(Panel(final_answer, title="[bold green]Final Answer[/bold green]"))


if __name__ == "__main__":
    main()
