#!/usr/bin/env python3
"""CLI entry point for eroasmr-scraper."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from eroasmr_scraper import __version__
from eroasmr_scraper.config import settings
from eroasmr_scraper.scraper import EroAsmrScraper
from eroasmr_scraper.storage import VideoStorage

app = typer.Typer(
    name="eroasmr-scraper",
    help="Video metadata scraper for eroasmr.com with Neo4j export support",
)
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging.

    Args:
        verbose: Enable debug logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show version and exit"),
    ] = False,
) -> None:
    """eroasmr-scraper - Video metadata scraper."""
    if version:
        console.print(f"eroasmr-scraper version {__version__}")
        raise typer.Exit()


@app.command()
def full(
    pages: Annotated[
        str | None,
        typer.Option("--pages", "-p", help="Page range (e.g., '1-10' or '5')"),
    ] = None,
    reverse: Annotated[
        bool,
        typer.Option("--reverse", "-r", help="Scrape from oldest to newest"),
    ] = False,
    no_details: Annotated[
        bool,
        typer.Option("--no-details", help="Skip detail page scraping"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable debug logging"),
    ] = False,
) -> None:
    """Full scrape - scrape all pages.

    Use --reverse to scrape from oldest to newest (starts from last page).
    """
    setup_logging(verbose)

    # Parse page range
    start_page = 1
    end_page = None

    if pages:
        if "-" in pages:
            parts = pages.split("-")
            start_page = int(parts[0])
            end_page = int(parts[1]) if len(parts) > 1 else None
        else:
            start_page = int(pages)
            end_page = start_page

    scraper = EroAsmrScraper()

    async def run() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scraping...", total=None)

            async for update in scraper.scrape_full(
                start_page=start_page,
                end_page=end_page,
                reverse=reverse,
                with_details=not no_details,
            ):
                if update["type"] == "page":
                    progress.update(
                        task,
                        description=f"Page {update['page']}/{update['total_pages']}",
                        total=update["total_pages"],
                        completed=update["page"],
                    )
                    console.print(
                        f"  [green]+[/green] {update['new_videos']} new "
                        f"(total: {update['total_new']})"
                    )

                elif update["type"] == "detail_progress":
                    progress.update(
                        task,
                        description=f"Details: {update['details_scraped']}/{update['total_details']}",
                        total=update["total_details"],
                        completed=update["details_scraped"],
                    )

                elif update["type"] == "complete":
                    progress.update(task, description="Complete!")
                    console.print()
                    console.print(
                        f"[green]Scraping complete![/green] "
                        f"Videos: {update['total_videos']}, "
                        f"Details: {update['total_details']}"
                    )

    asyncio.run(run())


@app.command()
def update(
    reverse: Annotated[
        bool,
        typer.Option("--reverse", "-r", help="Continue from last position (oldest-first)"),
    ] = False,
    no_details: Annotated[
        bool,
        typer.Option("--no-details", help="Skip detail page scraping"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable debug logging"),
    ] = False,
) -> None:
    """Incremental update - scrape only new videos.

    Stops when encountering existing video (forward mode).
    Use --reverse to continue from last position.
    """
    setup_logging(verbose)

    scraper = EroAsmrScraper()

    async def run() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking for new videos...", total=None)

            async for update in scraper.scrape_incremental(
                with_details=not no_details,
                reverse=reverse,
            ):
                if update["type"] == "page":
                    progress.update(
                        task,
                        description=f"Page {update['page']}: +{update['new_videos']} new",
                    )

                elif update["type"] == "stopped":
                    progress.update(task, description="Stopped")
                    console.print()
                    if update["reason"] == "found_existing":
                        console.print(
                            f"[yellow]Found existing video at page {update['page']}[/yellow]"
                        )
                    console.print(f"Total new videos: {update['total_new']}")
                    return

                elif update["type"] == "complete":
                    progress.update(task, description="Complete!")
                    console.print()
                    console.print(
                        f"[green]Update complete![/green] "
                        f"New videos: {update['total_new']}, "
                        f"Details: {update['total_details']}"
                    )

    asyncio.run(run())


@app.command()
def retry(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable debug logging"),
    ] = False,
) -> None:
    """Retry failed URLs."""
    setup_logging(verbose)

    scraper = EroAsmrScraper()

    async def run() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Retrying failed URLs...", total=None)

            async for update in scraper.retry_failed():
                if update["type"] == "retry_success":
                    console.print(f"  [green]✓[/green] {update['url']}")
                elif update["type"] == "retry_failed":
                    console.print(f"  [red]✗[/red] {update['url']}: {update['error']}")
                elif update["type"] == "complete":
                    progress.update(task, description="Complete!")
                    console.print()
                    console.print(
                        f"Retried: {update['retried']}, Success: {update['success']}"
                    )

    asyncio.run(run())


@app.command()
def stats() -> None:
    """Show database statistics."""
    storage = VideoStorage()
    stats = storage.get_stats()

    table = Table(title="Database Statistics")
    table.add_column("Item", style="cyan")
    table.add_column("Count", justify="right", style="green")

    table.add_row("Total Videos", str(stats["videos"]))
    table.add_row("Videos with Details", str(stats["videos_with_details"]))
    table.add_row("Tags", str(stats["tags"]))
    table.add_row("Categories", str(stats["categories"]))
    table.add_row("Video-Tag Relations", str(stats["video_tags"]))
    table.add_row("Related Video Relations", str(stats["video_related"]))
    table.add_row("Failed URLs", str(stats["failed_urls"]))

    console.print(table)

    # Show progress if any
    progress = storage.get_progress()
    if progress:
        console.print()
        progress_table = Table(title="Last Scrape Progress")
        progress_table.add_column("Field", style="cyan")
        progress_table.add_column("Value", style="yellow")

        progress_table.add_row("Mode", progress.mode)
        progress_table.add_row("Phase", progress.phase)
        progress_table.add_row("Last Page", str(progress.last_page))
        progress_table.add_row("Total Pages", str(progress.total_pages or "Unknown"))
        progress_table.add_row("Last Updated", progress.last_updated.strftime("%Y-%m-%d %H:%M:%S"))

        console.print(progress_table)


@app.command()
def export(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Export format: neo4j, jsonl"),
    ] = "neo4j",
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output directory/file"),
    ] = "./neo4j_import/",
) -> None:
    """Export data for Neo4j or other formats."""
    storage = VideoStorage()

    if format == "neo4j":
        output_path = Path(output)
        console.print(f"Exporting to Neo4j CSV format: {output_path}")

        files = storage.export_for_neo4j(str(output_path))

        console.print("[green]Export complete![/green]")
        for name, path in files.items():
            console.print(f"  {name}: {path}")

    elif format == "jsonl":
        import json

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        console.print(f"Exporting to JSONL: {output_path}")

        videos = list(storage.db["videos"].rows)

        with open(output_path, "w") as f:
            for video in videos:
                f.write(json.dumps(video, default=str) + "\n")

        console.print(f"[green]Export complete![/green] {len(videos)} videos")

    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        raise typer.Exit(1)


@app.command()
def clear_progress() -> None:
    """Clear scraping progress (for fresh start)."""
    storage = VideoStorage()
    storage.clear_progress()
    console.print("[green]Progress cleared.[/green]")


@app.command()
def refresh_durations(
    pages: Annotated[
        str | None,
        typer.Option("--pages", "-p", help="Page range (e.g., '1-10' or '5')"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable debug logging"),
    ] = False,
) -> None:
    """Refresh duration values for all existing videos.

    Re-scrapes list pages and updates duration fields in the database.
    Useful when the parser has been fixed or updated.
    """
    setup_logging(verbose)

    # Parse page range
    start_page = 1
    end_page = None

    if pages:
        if "-" in pages:
            parts = pages.split("-")
            start_page = int(parts[0])
            end_page = int(parts[1]) if len(parts) > 1 else None
        else:
            start_page = int(pages)
            end_page = start_page

    scraper = EroAsmrScraper()

    async def run() -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Refreshing durations...", total=None)

            async for update in scraper.refresh_durations(
                start_page=start_page,
                end_page=end_page,
            ):
                if update["type"] == "page":
                    progress.update(
                        task,
                        description=f"Page {update['page']}/{update['total_pages']}",
                        total=update["total_pages"],
                        completed=update["page"],
                    )
                    console.print(
                        f"  [cyan]~[/cyan] {update['videos_processed']} videos processed"
                    )

                elif update["type"] == "complete":
                    progress.update(task, description="Complete!")
                    console.print()
                    console.print(
                        f"[green]Duration refresh complete![/green] "
                        f"Total processed: {update['total_processed']}"
                    )

    asyncio.run(run())


if __name__ == "__main__":
    app()
