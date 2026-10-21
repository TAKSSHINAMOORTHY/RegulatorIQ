"""Command-line interface for RBI corpus acquisition."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config.paths import LEGAL_DOCS_DIR
from config.settings import settings
from ingest.discover import (
    RSS_FEEDS,
    SEED_LISTINGS,
    DocumentCandidate,
    RbiRobotGuard,
    parse_listing_html,
    parse_rss_feed,
)
from ingest.download import CircuitBreaker, PoliteDownloader
from ingest.manifest import export_manifest_parquet, load_manifest_records
from ingest.report import generate_corpus_report

app = typer.Typer(help="RegulatorIQ Official RBI Corpus Ingestion CLI")
console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ingest")


def fetch_terms_and_disclaimer(guard: RbiRobotGuard, downloader: PoliteDownloader) -> None:
    """Fetch terms and disclaimer page from RBI and save to docs/legal/rbi_terms.html."""
    terms_url = "https://www.rbi.org.in/Scripts/Disclaimer.aspx"
    target_file = LEGAL_DOCS_DIR / "rbi_terms.html"
    try:
        resp = downloader.client.get(terms_url, timeout=settings.TIMEOUT)
        if resp.status_code == 200:
            target_file.write_text(resp.text, encoding="utf-8")
            logger.info("Saved official RBI terms and disclaimer to docs/legal/rbi_terms.html")
        else:
            target_file.write_text(
                f"<!-- Terms page returned HTTP {resp.status_code} -->",
                encoding="utf-8",
            )
    except Exception as e:
        logger.warning(f"Could not fetch RBI terms page: {e}")
        target_file.write_text(f"<!-- Terms page fetch error: {e} -->", encoding="utf-8")


@app.command()
def acquire(
    max_docs: Optional[int] = typer.Option(
        None,
        "--max-docs",
        help="Maximum documents to download for testing or capped runs",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Discover and record without downloading file payloads",
    ),
) -> None:
    """Run full polite acquisition of official RBI regulatory documents."""
    console.print("[bold blue]Starting RegulatorIQ Official RBI Corpus Acquisition...[/bold blue]")

    guard = RbiRobotGuard()
    breaker = CircuitBreaker()
    downloader = PoliteDownloader(robot_guard=guard, circuit_breaker=breaker)

    limit = max_docs or settings.MAX_DOCS

    # Step 1: Robots.txt & Terms
    console.print("[cyan]Step 1/4: Obeying robots.txt and fetching legal notices...[/cyan]")
    guard.fetch_and_save(downloader.client, "rbi.org.in", "https://www.rbi.org.in/robots.txt")
    guard.fetch_and_save(
        downloader.client, "website.rbi.org.in", "https://website.rbi.org.in/robots.txt"
    )
    fetch_terms_and_disclaimer(guard, downloader)

    # Step 2: Discovery
    console.print(
        "[cyan]Step 2/4: Discovering documents from official seeds and RSS feeds...[/cyan]"
    )
    candidates: list[DocumentCandidate] = []
    seen_urls: set[str] = set()

    # Discover from RSS feeds first (fast & reliable)
    for doc_type, feed_url in RSS_FEEDS.items():
        try:
            resp = downloader.client.get(feed_url, timeout=settings.TIMEOUT)
            if resp.status_code == 200:
                feed_cands = parse_rss_feed(resp.text, doc_type)
                for c in feed_cands:
                    if c.file_url not in seen_urls:
                        seen_urls.add(c.file_url)
                        candidates.append(c)
        except Exception as e:
            logger.warning(f"Error reading RSS feed {feed_url}: {e}")

    # Discover from Seed listings
    for doc_type, urls in SEED_LISTINGS.items():
        for url in urls:
            try:
                resp = downloader.client.get(url, timeout=settings.TIMEOUT)
                if resp.status_code == 200:
                    page_cands = parse_listing_html(resp.text, url, doc_type)
                    for c in page_cands:
                        if c.file_url not in seen_urls:
                            seen_urls.add(c.file_url)
                            candidates.append(c)
            except Exception as e:
                logger.warning(f"Error fetching seed listing {url}: {e}")

    console.print(f"[green]Discovered {len(candidates)} document candidates.[/green]")

    if limit:
        candidates = candidates[:limit]
        console.print(f"[yellow]Capped to {len(candidates)} documents by --max-docs.[/yellow]")

    # Step 3: Resumable Downloads
    console.print("[cyan]Step 3/4: Downloading payloads with polite rate limits...[/cyan]")
    existing_records = {r.doc_id: r for r in load_manifest_records() if r.status == "ok"}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading...", total=len(candidates))
        for cand in candidates:
            if cand.doc_id in existing_records:
                progress.advance(task)
                continue

            if not dry_run:
                downloader.download_candidate(cand)
            progress.advance(task)

    # Step 4: Export Parquet and Report
    console.print("[cyan]Step 4/4: Exporting manifest and generating audit report...[/cyan]")
    export_manifest_parquet()
    report = generate_corpus_report()

    console.print(
        f"[bold green]Corpus Acquisition Finished! Total valid documents: {report['successful_documents']}[/bold green]"
    )


@app.command()
def resume() -> None:
    """Resume an interrupted corpus acquisition run."""
    acquire(max_docs=settings.MAX_DOCS, dry_run=False)


if __name__ == "__main__":
    app()
