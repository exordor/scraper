#!/usr/bin/env python3
"""Scrape only detail pages for existing zhumianwang videos.

Skips the list phase and directly scrapes detail pages for videos
that don't have detail_scraped_at set.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.sites.zhumianwang.scraper import ZhumianwangScraper
from eroasmr_scraper.sites.zhumianwang.models import VideoDetail, Tag, RelatedVideo

console = Console()


async def scrape_details_only(limit: int | None = None):
    """Scrape detail pages for videos without details."""
    storage = VideoStorage(site_id="zhumianwang")
    scraper = ZhumianwangScraper(storage=storage)

    # Get videos without details
    videos = storage.get_videos_without_details(limit=limit or 100000)
    total = len(videos)

    if not videos:
        console.print("[green]All videos already have details![/green]")
        return

    console.print(f"[cyan]Found {total} videos without details[/cyan]")

    async with scraper._get_client() as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scraping details...", total=total)

            for i, video in enumerate(videos, 1):
                progress.update(task, completed=i, description=f"Detail: {video['slug'][:30]}")

                try:
                    detail = await scraper.scrape_detail_page(client, video)

                    if detail:
                        # Save video detail
                        detail_obj = VideoDetail(**{k: v for k, v in detail.items() if not k.startswith("_")})
                        storage.upsert_video_detail(detail_obj)

                        # Save tags
                        for tag in detail.get("_tags", []):
                            tag_obj = Tag(**tag)
                            storage.upsert_tag(tag_obj)
                            storage.add_video_tag(video["slug"], tag["slug"])

                        # Save related videos
                        for rel in detail.get("_related", []):
                            rel_obj = RelatedVideo(**rel)
                            storage.add_related_video(video["slug"], rel_obj)

                except Exception as e:
                    console.print(f"[red]Error scraping {video['slug']}: {e}[/red]")

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

    console.print(f"[green]Complete! Scraped {total} detail pages[/green]")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape detail pages only")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Limit number of videos")
    args = parser.parse_args()

    asyncio.run(scrape_details_only(limit=args.limit))
