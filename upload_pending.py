#!/usr/bin/env python3
"""Upload pending files from download directory with concurrent uploads."""

import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from eroasmr_scraper.config import settings
from eroasmr_scraper.models import StorageLocation
from eroasmr_scraper.storage import VideoStorage
from eroasmr_scraper.telegram_uploader import TelegramUploader

# Thread-safe counter
class Counter:
    def __init__(self):
        self.value = 0
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            self.value += 1
            return self.value


def upload_file_with_retry(args, max_retries=3):
    """Upload a single file with retry logic for rate limits."""
    file_path, download_dir, uploader, storage, counter, total = args
    slug = file_path.stem
    idx = counter.increment()

    # Find thumbnail
    thumbnail_path = download_dir / f"{slug}_thumb.jpg"

    for attempt in range(max_retries):
        print(f"[{idx}/{total}] Uploading: {slug}" + (f" (retry {attempt})" if attempt > 0 else ""), flush=True)

        result = uploader.upload(
            file_path,
            slug,
            thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
        )

        if result.success:
            print(f"[{idx}/{total}] ✓ {slug}: {result.location_url}", flush=True)

            # Record to storage_locations table for dashboard
            try:
                location = StorageLocation(
                    slug=slug,
                    storage_type="telegram",
                    location_id=result.location_id or "",
                    location_url=result.location_url,
                    metadata=result.metadata,
                )
                storage.add_storage_location(location)
            except Exception:
                print(f"[{idx}/{total}] ⚠ {slug}: Record exists", flush=True)

            # Delete file after successful upload
            try:
                file_path.unlink()
                if thumbnail_path.exists():
                    thumbnail_path.unlink()
            except Exception:
                pass

            return (True, slug)

        # Check for rate limit error
        error_msg = str(result.error) if result.error else ""
        if "too Many Requests" in error_msg or "Too Many Requests" in error_msg:
            # Extract retry time from error message
            match = re.search(r"retry after (\d+)", error_msg)
            wait_time = int(match.group(1)) if match else 10
            wait_time = min(wait_time, 30)  # Cap at 30 seconds
            print(f"[{idx}/{total}] ⏳ Rate limited, waiting {wait_time}s...", flush=True)
            time.sleep(wait_time)
            continue
        else:
            # Non-rate-limit error, don't retry
            print(f"[{idx}/{total}] ✗ {slug}: {result.error}", flush=True)
            return (False, slug)

    print(f"[{idx}/{total}] ✗ {slug}: Max retries exceeded", flush=True)
    return (False, slug)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Upload pending files")
    parser.add_argument("--workers", "-w", type=int, default=3, help="Number of concurrent uploads (default: 3)")
    args = parser.parse_args()

    download_dir = Path("/root/telegram-upload-service/data/downloads")

    # Get all mp4 files
    pending_files = sorted(download_dir.glob("*.mp4"))
    print(f"Found {len(pending_files)} pending files to upload", flush=True)
    print(f"Using {args.workers} concurrent upload workers", flush=True)

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

    counter = Counter()
    total = len(pending_files)
    success_count = 0
    fail_count = 0

    # Prepare arguments for each file
    tasks = [
        (file_path, download_dir, uploader, storage, counter, total)
        for file_path in pending_files
    ]

    # Upload concurrently
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(upload_file_with_retry, task): task for task in tasks}

        for future in as_completed(futures):
            try:
                success, slug = future.result()
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print(f"Exception: {e}", flush=True)
                fail_count += 1

    print(f"\n{'='*50}", flush=True)
    print(f"Upload complete: {success_count} success, {fail_count} failed", flush=True)


if __name__ == "__main__":
    main()
