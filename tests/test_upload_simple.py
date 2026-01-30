"""
Simple Upload Module Test Script

Tests upload without interactive input.
"""

import asyncio
import sys
import os
import time

# Add paths
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(root_path, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, root_path)

from database.manager import DatabaseManager
from upload_module import UploadManager

TEST_DB_PATH = 'test_upload.db'
DOWNLOAD_DIR = 'D:\\Projects\\smart-downloader\\downloads'


async def run_simple_test():
    """Run simple upload test without interactive input."""
    print("="*80)
    print("SIMPLE UPLOAD TEST".center(80))
    print("="*80 + "\n")

    # Initialize database
    if not os.path.exists(TEST_DB_PATH):
        print("[ERROR] Test database not found. Run setup first.")
        return

    db = DatabaseManager(TEST_DB_PATH)

    # Get first downloaded item
    downloads = db.get_all_downloads(status='downloaded')

    if not downloads:
        print("[ERROR] No items to upload")
        return

    download = downloads[0]
    download_id = download['id']

    print(f"[INFO] Testing upload for ID {download_id}: {download['title']}")
    print(f"[INFO] File path: {download['file_path']}")
    print(f"[INFO] File size: {download['file_size']} bytes")

    # Initialize upload manager
    from dotenv import load_dotenv
    load_dotenv()

    manager = UploadManager(
        db=db,
        download_dir=DOWNLOAD_DIR,
        uploader=None
    )

    print("[OK] Upload manager initialized\n")

    # Start processor
    print("[START] Starting upload processor...")
    await manager.start_processor(check_interval=1)

    # Monitor progress
    start_time = time.time()
    last_print = start_time

    while True:
        await asyncio.sleep(1)

        # Print status every 3 seconds
        if time.time() - last_print >= 3:
            elapsed = int(time.time() - start_time)

            # Get current download status
            current = db.get_download(download_id)

            print(f"[{elapsed}s] ID={download_id} Status={current['status']} "
                  f"Progress={current.get('progress', 0)}% "
                  f"Speed={current.get('upload_speed', 0)/1024 if current.get('upload_speed') else 0:.1f} KB/s "
                  f"ETA={current.get('eta_seconds', 0)}s")

            last_print = time.time()

        # Check if done
        current = db.get_download(download_id)
        if current['status'] in ['uploaded', 'failed']:
            break

    total_time = time.time() - start_time

    # Final result
    current = db.get_download(download_id)

    print(f"\n{'='*80}")
    print(f"RESULT: {current['status']}".center(80))
    print(f"{'='*80}")

    if current['status'] == 'uploaded':
        print(f"[SUCCESS] Upload completed in {total_time:.1f} seconds")
        print(f"[FILE_ID] {current['file_id']}")

        # Check file deleted
        if os.path.exists(current['file_path']):
            print(f"[WARNING] Local file still exists")
        else:
            print(f"[OK] Local file deleted")

    elif current['status'] == 'failed':
        print(f"[FAILED] {current.get('error_message', 'Unknown error')}")

    # Cleanup
    await manager.stop_processor()
    await manager.disconnect()

    print(f"\n[DONE] Test completed\n")


if __name__ == '__main__':
    try:
        asyncio.run(run_simple_test())
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED]")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
