#!/usr/bin/env python3
"""CLI entry point for eroasmr-scraper."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Literal

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
from eroasmr_scraper.downloader import VideoDownloader
from eroasmr_scraper.parallel_pipeline import ParallelPipeline
from eroasmr_scraper.pipeline import DownloadUploadPipeline
from eroasmr_scraper.scraper import EroAsmrScraper
from eroasmr_scraper.sites.zhumianwang.scraper import ZhumianwangScraper
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.telegram_uploader import TelegramUploader
from eroasmr_scraper.uploader import MockUploader, Uploader
from eroasmr_scraper.factory import ScraperFactory

app = typer.Typer(
    name="eroasmr-scraper",
    help="Video metadata scraper for eroasmr.com with Neo4j export support",
)
console = Console()

# Site ID type for CLI options
SiteChoice = Annotated[
    Literal["eroasmr", "zhumianwang"],
    typer.Option("--site", "-s", help="Site to scrape (eroasmr, zhumianwang)"),
]


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
def sites() -> None:
    """List available sites."""
    table = Table(title="Available Sites")
    table.add_column("Site ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Status", style="yellow")

    # Check each site
    sites_info = [
        ("eroasmr", "EroAsmr", settings.sites.eroasmr.enabled),
        ("zhumianwang", "助眠网", settings.sites.zhumianwang.enabled),
    ]

    for site_id, name, enabled in sites_info:
        status = "[green]enabled[/green]" if enabled else "[red]disabled[/red]"
        table.add_row(site_id, name, status)

    console.print(table)
    console.print()
    console.print(f"[dim]Default site: {settings.default_site}[/dim]")


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
    with_downloads: Annotated[
        bool,
        typer.Option("--with-downloads", help="Scrape download links (zhumianwang only, requires auth)"),
    ] = False,
    site: SiteChoice = "eroasmr",  # type: ignore
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Enable debug logging"),
    ] = False,
) -> None:
    """Full scrape - scrape all pages.

    Use --reverse to scrape from oldest to newest (starts from last page).
    Use --site to specify the site (eroasmr, zhumianwang).
    Use --with-downloads to scrape download links (zhumianwang only, requires login cookies).
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

    # Create storage and scraper for the selected site
    storage = VideoStorage(site_id=site)

    if site == "zhumianwang":
        scraper = ZhumianwangScraper(storage=storage)
    else:
        scraper = EroAsmrScraper(storage=storage)

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

            # Build kwargs for scrape_full
            scrape_kwargs = {
                "start_page": start_page,
                "end_page": end_page,
                "reverse": reverse,
                "with_details": not no_details,
            }
            # Only pass with_downloads for zhumianwang
            if site == "zhumianwang" and with_downloads:
                scrape_kwargs["with_downloads"] = True

            async for update in scraper.scrape_full(**scrape_kwargs):
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

                elif update["type"] == "download_progress":
                    progress.update(
                        task,
                        description=f"Downloads: {update['downloads_scraped']}/{update['total_downloads']}",
                        total=update["total_downloads"],
                        completed=update["downloads_scraped"],
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

                elif update["type"] == "complete":
                    progress.update(task, description="Complete!")
                    console.print()
                    stop_reason = update.get("stop_reason")
                    if stop_reason == "found_existing":
                        console.print("[yellow]Found existing video, stopped early[/yellow]")
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
def stats(
    site: SiteChoice = "eroasmr",  # type: ignore
) -> None:
    """Show database statistics."""
    storage = VideoStorage(site_id=site)
    stats = storage.get_stats()

    table = Table(title=f"Database Statistics [{site}]")
    table.add_column("Item", style="cyan")
    table.add_column("Count", justify="right", style="green")

    table.add_row("Site ID", stats.get("site_id", site))
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
def verify() -> None:
    """Verify database data integrity."""
    storage = VideoStorage()

    issues: list[str] = []

    # Check for missing fields
    total = storage.db["videos"].count

    missing_duration = storage.db["videos"].count_where("duration IS NULL")
    missing_duration_seconds = storage.db["videos"].count_where("duration_seconds IS NULL")
    missing_views = storage.db["videos"].count_where("views = 0 OR views IS NULL")
    missing_title = storage.db["videos"].count_where("title IS NULL OR title = ''")

    if missing_duration > 0:
        issues.append(f"Missing duration: {missing_duration}/{total} videos")
    if missing_duration_seconds > 0:
        issues.append(f"Missing duration_seconds: {missing_duration_seconds}/{total} videos")
    if missing_views > 0:
        issues.append(f"Missing views: {missing_views}/{total} videos")
    if missing_title > 0:
        issues.append(f"Missing title: {missing_title}/{total} videos")

    # Show results
    if issues:
        console.print("[red]Data integrity issues found:[/red]\n")
        for issue in issues:
            console.print(f"  [red]✗[/red] {issue}")

        console.print(f"\n[yellow]Run 'python main.py refresh-durations' to fix missing data[/yellow]")
        raise typer.Exit(1)
    else:
        console.print("[green]✓ Data integrity check passed![/green]")
        console.print(f"  All {total} videos have complete data.")


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


@app.command()
def download(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory for videos"),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of videos to download"),
    ] = None,
    retry: Annotated[
        bool,
        typer.Option("--retry", help="Retry failed downloads"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
) -> None:
    """Download videos from scraped data.

    Downloads all pending videos (not yet downloaded) to the output directory.
    Use --retry to retry previously failed downloads.

    Examples:
        eroasmr-scraper download                    # Download all pending
        eroasmr-scraper download --limit 10         # Download first 10
        eroasmr-scraper download --retry            # Retry failed downloads
        eroasmr-scraper download -o ./my_videos     # Custom output directory
    """
    setup_logging(verbose)

    # Set output directory
    output_dir = output or Path("data/downloads")
    archive_file = Path("data/download_archive.txt")

    storage = VideoStorage()
    downloader = VideoDownloader(
        storage=storage,
        output_dir=output_dir,
        archive_file=archive_file,
    )

    console.print(f"[cyan]Output directory:[/cyan] {output_dir}")
    console.print(f"[cyan]Archive file:[/cyan] {archive_file}")

    # Get pending count
    pending = storage.get_pending_downloads(limit=limit, include_failed=retry)
    total_pending = len(pending)

    if total_pending == 0:
        console.print("[yellow]No pending downloads.[/yellow]")
        if not retry:
            console.print("Use --retry to retry failed downloads.")
        return

    console.print(f"[cyan]Pending downloads:[/cyan] {total_pending}")
    console.print()

    # Run download
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading...", total=total_pending)

        completed = 0
        failed = 0

        for i, slug in enumerate(pending, 1):
            progress.update(
                task,
                description=f"Downloading {slug}...",
                completed=i - 1,
            )

            success, error = downloader.download_video(slug)

            if success:
                completed += 1
                console.print(f"  [green]✓[/green] {slug}")
            else:
                failed += 1
                console.print(f"  [red]✗[/red] {slug}: {error}")

        progress.update(task, completed=total_pending, description="Complete!")

    console.print()
    console.print(
        f"[green]Download complete![/green] "
        f"Completed: {completed}, Failed: {failed}"
    )


@app.command()
def download_stats() -> None:
    """Show download statistics."""
    storage = VideoStorage()
    stats = storage.get_download_stats()

    table = Table(title="Download Statistics")
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right", style="green")

    table.add_row("Total Videos", str(stats["total_videos"]))
    table.add_row("Not Started", str(stats["not_started"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Downloading", str(stats["downloading"]))
    table.add_row("Completed", str(stats["completed"]))
    table.add_row("Failed", str(stats["failed"]))

    console.print(table)

    # Show progress percentage
    if stats["total_videos"] > 0:
        progress_pct = stats["completed"] / stats["total_videos"] * 100
        console.print()
        console.print(f"Progress: {progress_pct:.1f}% complete")


@app.command()
def reset_downloads(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation"),
    ] = False,
) -> None:
    """Reset download status (clear downloads table and archive).

    Useful when:
    - Moving to a new server and need to re-download videos
    - Downloaded files were deleted and need to be re-downloaded
    - Want to start fresh with downloads

    This will:
    - Delete all records from downloads table
    - Delete all records from storage_locations table
    - Clear the download_archive.txt file

    Videos metadata (videos table) will NOT be affected.
    """
    storage = VideoStorage()
    archive_file = Path("data/download_archive.txt")

    # Get current stats
    download_count = storage.db["downloads"].count
    storage_count = storage.db["storage_locations"].count
    video_count = storage.db["videos"].count

    console.print(f"[cyan]Videos in database:[/cyan] {video_count}")
    console.print(f"[cyan]Download records:[/cyan] {download_count}")
    console.print(f"[cyan]Storage locations:[/cyan] {storage_count}")
    console.print()

    if not yes:
        confirm = typer.confirm(
            "This will reset all download status. Continue?",
            default=False,
        )
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

    # Clear downloads table (use raw SQL to ensure commit)
    with storage.db.conn:
        storage.db.conn.execute("DELETE FROM downloads")
        storage.db.conn.execute("DELETE FROM storage_locations")
    console.print("[green]✓[/green] Cleared downloads and storage_locations tables")

    # Clear archive file
    if archive_file.exists():
        archive_file.unlink()
        console.print("[green]✓[/green] Deleted download archive file")

    console.print()
    console.print("[green]Reset complete![/green] Run 'download' or 'pipeline' to start downloading.")


def _get_uploaders() -> list[Uploader]:
    """Get list of configured uploaders.

    Returns uploaders based on configuration. If no real uploaders are
    configured, returns MockUploader for testing.

    Configure Telegram via environment variables:
        EROASMR_TELEGRAM__TENANT_ID=your-tenant-id
        EROASMR_TELEGRAM__UPLOAD_SERVICE_URL=http://localhost:8000
        EROASMR_TELEGRAM__FILE_PATH_MAP={"data/downloads": "/app/data/downloads"}
    """
    uploaders_list: list[Uploader] = []
    storage = VideoStorage()

    # Add Telegram uploader if configured
    if settings.telegram.tenant_id:
        telegram = TelegramUploader(
            upload_service_url=settings.telegram.upload_service_url,
            tenant_id=settings.telegram.tenant_id,
            caption_template=settings.telegram.caption_template,
            parse_mode=settings.telegram.parse_mode,
            file_path_map=settings.telegram.file_path_map,
            storage=storage,
        )
        if telegram.is_ready():
            uploaders_list.append(telegram)

    # Add mock uploader if no real uploaders configured
    if not uploaders_list:
        uploaders_list.append(MockUploader())

    return uploaders_list


@app.command()
def pipeline(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory for videos"),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of videos to process"),
    ] = None,
    retry: Annotated[
        bool,
        typer.Option("--retry", help="Retry failed downloads"),
    ] = False,
    keep_files: Annotated[
        bool,
        typer.Option("--keep", "-k", help="Keep local files after upload"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
) -> None:
    """Download and upload videos in a pipeline.

    Downloads videos and uploads them to all configured platforms.
    By default, deletes local files after successful uploads.

    Examples:
        eroasmr-scraper pipeline                    # Process all pending
        eroasmr-scraper pipeline --limit 10         # Process first 10
        eroasmr-scraper pipeline --keep             # Keep local files
        eroasmr-scraper pipeline -o ./videos -n 5   # Custom output, 5 videos
    """
    setup_logging(verbose)

    output_dir = output or Path("data/downloads")
    archive_file = Path("data/download_archive.txt")

    storage = VideoStorage()
    downloader = VideoDownloader(
        storage=storage,
        output_dir=output_dir,
        archive_file=archive_file,
    )

    # Get configured uploaders
    uploaders = _get_uploaders()

    if not uploaders:
        console.print("[yellow]No uploaders configured. Using mock uploader for testing.[/yellow]")
        console.print("To add real uploaders, implement Uploader subclasses.")

    # Create pipeline
    pipeline_instance = DownloadUploadPipeline(
        storage=storage,
        downloader=downloader,
        uploaders=uploaders,
        delete_after_upload=not keep_files,
    )

    # Show configuration
    console.print(f"[cyan]Output directory:[/cyan] {output_dir}")
    console.print(f"[cyan]Uploaders:[/cyan] {', '.join(u.storage_type for u in uploaders)}")
    console.print(f"[cyan]Delete after upload:[/cyan] {not keep_files}")
    console.print()

    # Check uploader status
    status = pipeline_instance.get_uploader_status()
    for storage_type, ready in status.items():
        icon = "[green]✓[/green]" if ready else "[red]✗[/red]"
        console.print(f"  {icon} {storage_type}: {'ready' if ready else 'not configured'}")

    console.print()

    # Run pipeline
    stats = pipeline_instance.process_all(limit=limit, retry_failed=retry)

    # Show summary
    console.print()
    console.print("[green]Pipeline complete![/green]")
    console.print(f"  Downloaded: {stats['downloaded']}")
    console.print(f"  Upload success: {stats['upload_success']}")
    console.print(f"  Upload partial: {stats['upload_partial']}")
    console.print(f"  Upload failed: {stats['upload_failed']}")
    console.print(f"  Download failed: {stats['download_failed']}")


@app.command()
def parallel(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory for videos"),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of videos to process"),
    ] = None,
    retry: Annotated[
        bool,
        typer.Option("--retry", help="Retry failed downloads"),
    ] = False,
    keep_files: Annotated[
        bool,
        typer.Option("--keep", "-k", help="Keep local files after upload"),
    ] = False,
    queue_size: Annotated[
        int,
        typer.Option("--queue-size", help="Max items in download queue"),
    ] = 20,
    upload_workers: Annotated[
        int,
        typer.Option("--upload-workers", "-w", help="Number of concurrent upload workers"),
    ] = 3,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
) -> None:
    """Run parallel download-upload pipeline.

    Downloads and uploads run concurrently:
    - Downloader continuously downloads videos
    - Uploaders continuously upload completed downloads
    - Files are deleted after successful uploads

    This is more efficient than sequential pipeline for large batches.

    Examples:
        eroasmr-scraper parallel                    # Process all pending
        eroasmr-scraper parallel --limit 100        # Process 100 videos
        eroasmr-scraper parallel --keep             # Keep local files
        eroasmr-scraper parallel --queue-size 20    # Larger download buffer
        eroasmr-scraper parallel --upload-workers 5 # 5 concurrent uploads
    """
    setup_logging(verbose)

    output_dir = output or Path("data/downloads")
    archive_file = Path("data/download_archive.txt")

    storage = VideoStorage()
    downloader = VideoDownloader(
        storage=storage,
        output_dir=output_dir,
        archive_file=archive_file,
    )

    # Get configured uploaders
    uploaders_list = _get_uploaders()

    if not uploaders_list:
        console.print("[yellow]No uploaders configured. Using mock uploader for testing.[/yellow]")

    # Create parallel pipeline
    pipeline_instance = ParallelPipeline(
        storage=storage,
        downloader=downloader,
        uploaders=uploaders_list,
        download_queue_size=queue_size,
        upload_queue_size=queue_size * 2,
        upload_workers=upload_workers,
        delete_after_upload=not keep_files,
    )

    # Show configuration
    console.print(f"[cyan]Output directory:[/cyan] {output_dir}")
    console.print(f"[cyan]Uploaders:[/cyan] {', '.join(u.storage_type for u in uploaders_list)}")
    console.print(f"[cyan]Download queue size:[/cyan] {queue_size}")
    console.print(f"[cyan]Upload workers:[/cyan] {upload_workers}")
    console.print(f"[cyan]Delete after upload:[/cyan] {not keep_files}")
    console.print()

    # Check uploader status
    for uploader in uploaders_list:
        ready = uploader.is_ready()
        icon = "[green]✓[/green]" if ready else "[red]✗[/red]"
        console.print(f"  {icon} {uploader.storage_type}: {'ready' if ready else 'not configured'}")

    console.print()

    # Run pipeline
    stats = asyncio.run(pipeline_instance.run(limit=limit, retry_failed=retry))

    # Show summary
    console.print()
    console.print("[green]Parallel pipeline complete![/green]")
    console.print(f"  Total: {stats['total']}")
    console.print(f"  Downloaded: {stats['downloaded']}")
    console.print(f"  Download failed: {stats['download_failed']}")
    console.print(f"  Uploaded: {stats['uploaded']}")
    console.print(f"  Upload failed: {stats['upload_failed']}")
    console.print(f"  Files deleted: {stats['files_deleted']}")


@app.command()
def uploaders() -> None:
    """Show status of configured uploaders."""
    uploaders_list = _get_uploaders()

    table = Table(title="Uploader Status")
    table.add_column("Storage Type", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Description")

    for uploader in uploaders_list:
        ready = uploader.is_ready()
        status = "[green]Ready[/green]" if ready else "[red]Not Configured[/red]"
        desc = uploader.__class__.__name__
        table.add_row(uploader.storage_type, status, desc)

    # Show Telegram config status if not already in list
    telegram_in_list = any(u.storage_type == "telegram" for u in uploaders_list)
    if not telegram_in_list:
        table.add_row(
            "telegram",
            "[yellow]Not Configured[/yellow]",
            "[dim]Set EROASMR_TELEGRAM__TENANT_ID to enable[/dim]"
        )

    # Add placeholder for future uploaders
    future_uploaders = [
        ("google_drive", "GoogleDriveUploader", "Upload to Google Drive"),
    ]

    for storage_type, class_name, desc in future_uploaders:
        table.add_row(storage_type, "[dim]Not implemented[/dim]", f"[dim]{class_name}: {desc}[/dim]")

    console.print(table)
    console.print()
    console.print("[dim]Configure uploaders via environment variables (EROASMR_<NAME>__<FIELD>)[/dim]")
