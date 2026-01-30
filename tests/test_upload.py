"""
Upload Module Test Script

Tests the upload module with real files in the download directory.
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Add src and root to path
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(root_path, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, root_path)

from database.manager import DatabaseManager
from src.upload_module import UploadManager


# Test database path
TEST_DB_PATH = 'test_upload.db'
DOWNLOAD_DIR = 'D:\\Projects\\smart-downloader\\downloads'


def print_banner():
    """Print test banner."""
    print("\n" + "="*80)
    print("UPLOAD MODULE TEST".center(80))
    print("="*80 + "\n")


def print_status(db):
    """Print current database status."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, status, progress, upload_speed, eta_seconds,
                   file_size, file_id, error_message
            FROM downloads
            ORDER BY id
        """)
        rows = cursor.fetchall()

        print("\n" + "-"*80)
        print(f"{'ID':<4} {'Title':<25} {'Status':<12} {'Prog':<6} {'Speed (MB/s)':<12} {'ETA':<8} {'File ID':<15}")
        print("-"*80)

        for row in rows:
            id, title, status, progress, upload_speed, eta, file_size, file_id, error = row
            prog = f"{progress}%" if progress else "0%"
            speed = f"{upload_speed/(1024*1024):.2f}" if upload_speed else "N/A"
            eta_s = f"{eta}s" if eta else "N/A"
            fid = file_id[:15] if file_id else "NULL"

            print(f"{id:<4} {title[:23]:<25} {status:<12} {prog:<6} {speed:<12} {eta_s:<8} {fid:<15}")

            if error:
                print(f"     Error: {error}")

        print("-"*80 + "\n")


async def test_single_upload(manager: UploadManager, db: DatabaseManager, download_id: int):
    """Test uploading a single file."""
    print(f"\n{'='*80}")
    print(f"Testing Upload for Download ID: {download_id}")
    print(f"{'='*80}\n")

    # Get download details
    download = db.get_download(download_id)
    if not download:
        print(f"[ERROR] Download {download_id} not found")
        return

    print(f"[FILE] {download['title']}")
    print(f"[PATH] {download['file_path']}")
    print(f"[SIZE] {download['file_size'] / (1024*1024):.2f} MB")
    print(f"[STATUS] {download['status']}")
    print()

    # Check file exists
    if not os.path.exists(download['file_path']):
        print(f"[ERROR] File not found: {download['file_path']}")
        return

    # Test upload
    print("[START] Starting upload...")
    print_status(db)

    start_time = time.time()

    # Monitor progress
    while download['status'] in ['downloaded', 'uploading']:
        await asyncio.sleep(1)

        # Refresh download status
        download = db.get_download(download_id)

        # Print progress every 3 seconds
        if int(time.time() - start_time) % 3 == 0:
            progress = download.get('progress', 0)
            speed = download.get('upload_speed', 0)
            eta = download.get('eta_seconds', 0)

            print(f"[PROGRESS] {progress}% | "
                  f"Speed: {speed/(1024*1024):.2f} MB/s | "
                  f"ETA: {eta}s", end='\r')

    elapsed = time.time() - start_time

    # Final status
    print(f"\n\n[DONE] Upload completed in {elapsed:.1f} seconds")
    print_status(db)

    # Verify result
    download = db.get_download(download_id)
    if download['status'] == 'uploaded':
        print(f"[SUCCESS] File uploaded successfully")
        print(f"[FILE_ID] {download['file_id']}")

        # Check file was deleted
        if os.path.exists(download['file_path']):
            print(f"[WARNING] Local file still exists (should be deleted)")
        else:
            print(f"[CLEAN] Local file deleted successfully")

    elif download['status'] == 'failed':
        print(f"[FAILED] {download.get('error_message', 'Unknown error')}")


async def test_sequential_uploads(manager: UploadManager, db: DatabaseManager):
    """Test uploading multiple files sequentially."""
    print(f"\n{'='*80}")
    print("Testing Sequential Uploads (Pooler Mode)")
    print(f"{'='*80}\n")

    print("[START] Starting upload processor...")
    await manager.start_processor(check_interval=2)

    # Get all downloaded items
    downloads = db.get_all_downloads(status='downloaded')

    print(f"[INFO] Found {len(downloads)} items to upload")
    print_status(db)

    # Monitor progress
    start_time = time.time()
    last_check = start_time

    while True:
        await asyncio.sleep(2)

        # Print status every 5 seconds
        if time.time() - last_check >= 5:
            elapsed = time.time() - start_time
            print(f"\n[TIME] Elapsed: {int(elapsed)}s")
            print_status(db)
            last_check = time.time()

        # Check if all done
        active = db.get_all_downloads(status='uploading')
        downloaded = db.get_all_downloads(status='downloaded')

        if not active and not downloaded:
            break

    total_elapsed = time.time() - start_time
    print(f"\n[DONE] All uploads completed in {total_elapsed:.1f} seconds")
    print_status(db)

    # Stop processor
    await manager.stop_processor()


async def run_tests():
    """Run all upload tests."""
    print_banner()

    # Initialize test database
    if not os.path.exists(TEST_DB_PATH):
        print("[ERROR] Test database not found. Run test_upload_db.py first.")
        return

    db = DatabaseManager(TEST_DB_PATH)

    # Initialize upload manager
    print("[INIT] Initializing upload manager...")

    # Check for userbot credentials
    from dotenv import load_dotenv
    load_dotenv()

    api_id = os.getenv('UPLOADER_API_ID')
    api_hash = os.getenv('UPLOADER_API_HASH')
    phone = os.getenv('UPLOADER_PHONE')

    if not all([api_id, api_hash, phone]):
        print("[ERROR] Userbot credentials not found. Please set UPLOADER_API_ID, UPLOADER_API_HASH, UPLOADER_PHONE in .env")
        return

    manager = UploadManager(
        db=db,
        download_dir=DOWNLOAD_DIR,
        uploader=None  # Will create own from env vars
    )

    print("[OK] Upload manager initialized")
    print_status(db)

    # Menu
    print("\nTest Options:")
    print("1. Upload single file (manual)")
    print("2. Upload all files sequentially (pooler mode)")
    print("3. Exit")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == '1':
        # Single file test
        downloads = db.get_all_downloads(status='downloaded')
        if not downloads:
            print("[ERROR] No downloaded items found")
            return

        print("\nAvailable files:")
        for d in downloads:
            size_mb = d['file_size'] / (1024*1024) if d['file_size'] else 0
            print(f"  {d['id']}: {d['title']} ({size_mb:.2f} MB)")

        download_id = input("\nEnter download ID to upload: ").strip()
        try:
            download_id = int(download_id)
            await test_single_upload(manager, db, download_id)
        except ValueError:
            print("[ERROR] Invalid ID")

    elif choice == '2':
        # Sequential upload test
        await test_sequential_uploads(manager, db)

    # Cleanup
    await manager.disconnect()
    print("\n[DONE] Test completed")


if __name__ == '__main__':
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
