#!/usr/bin/env python3
"""Upload pending files from download directory."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import StorageLocation
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.telegram_uploader import TelegramUploader


def main():
    download_dir = Path("/root/telegram-upload-service/data/downloads")

    # Get all mp4 files
    pending_files = sorted(download_dir.glob("*.mp4"))
    print(f"Found {len(pending_files)} pending files to upload")

    if not pending_files:
        print("No pending files found.")
        return

    # Initialize storage and uploader
    storage = VideoStorage()
    uploader = TelegramUploader(
        upload_service_url=settings.telegram.upload_service_url,
        tenant_id=settings.telegram.tenant_id,
        caption_template=settings.telegram.caption_template,
        parse_mode=settings.telegram.parse_mode,
        file_path_map=settings.telegram.file_path_map,
        storage=storage,
    )

    if not uploader.is_ready():
        print("ERROR: Telegram uploader not configured")
        return

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(pending_files, 1):
        slug = file_path.stem
        print(f"\n[{i}/{len(pending_files)}] Uploading: {slug}")

        # Find thumbnail
        thumbnail_path = download_dir / f"{slug}_thumb.jpg"

        result = uploader.upload(
            file_path,
            slug,
            thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
        )

        if result.success:
            print(f"  ✓ Success: {result.location_url}")

            # Record to storage_locations table for dashboard
            location = StorageLocation(
                slug=slug,
                storage_type="telegram",
                location_id=result.location_id or "",
                location_url=result.location_url,
                metadata=result.metadata,
            )
            storage.add_storage_location(location)

            # Delete file after successful upload
            file_path.unlink()
            if thumbnail_path.exists():
                thumbnail_path.unlink()
            success_count += 1
        else:
            print(f"  ✗ Failed: {result.error}")
            fail_count += 1

    print(f"\n{'='*50}")
    print(f"Upload complete: {success_count} success, {fail_count} failed")


if __name__ == "__main__":
    main()
