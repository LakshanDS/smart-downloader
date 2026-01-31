# -*- coding: utf-8 -*-
"""
Test Script for Download Module

Tests all downloaders:
1. URL Detection
2. Crawler (Playwright)
3. yt-dlp
4. Direct
5. Torrent (magnet)

Also tests cancel functionality.
"""

import os
import sys
import time
import sqlite3
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test database path
TEST_DB = project_root / "test_downloads.db"

# Test URLs
TEST_URLS = {
    'crawler': 'https://abbdsm.com/video/138079/fireworks-bondage-rim-jobs-and-gagging-on-cock-a-lovely-weekend-in-nyc/',
    'youtube': 'https://youtube.com/shorts/pjT0ubmENWk?si=ZorjU6bkCpmAxtU4',
    'direct': 'http://ipv4.download.thinkbroadband.com/20MB.zip',
    'torrent': 'magnet:?xt=urn:btih:481EE6DC50FF043F4EFD83C9FAB6E15B133E51B8&dn=Newspaper+Collection+The+Hindu+29th+January+2026&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.zer0day.to%3A1337%2Fannounce&tr=udp%3A%2F%2Feddie4.nl%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=http%3A%2F%2Ftracker.openbittorrent.com%3A80%2Fannounce&tr=udp%3A%2F%2Fopentracker.i2p.rocks%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.internetwarriors.net%3A1337%2Fannounce&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969%2Fannounce&tr=udp%3A%2F%2Fcoppersurfer.tk%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.zer0day.to%3A1337%2Fannounce'
}


def create_test_database():
    """Create test database with same schema as production."""
    print("=" * 60)
    print("Creating test database...")
    print("=" * 60)

    # Remove existing test database
    if TEST_DB.exists():
        TEST_DB.unlink()
        print(f"Removed existing test database: {TEST_DB}")

    # Create new database
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()

    # Create downloads table with all columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            source TEXT,
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            error_message TEXT,
            file_size INTEGER,
            title TEXT,
            download_speed REAL,
            upload_speed REAL,
            eta_seconds INTEGER,
            message_id INTEGER,
            chat_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            priority INTEGER DEFAULT 0,
            can_pause BOOLEAN DEFAULT 1,
            paused BOOLEAN DEFAULT 0,
            pause_reason TEXT,
            file_id TEXT,
            file_path TEXT,
            cancelled INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

    print(f"[OK] Test database created: {TEST_DB}")
    print()


def add_test_downloads():
    """Add test downloads to database."""
    print("=" * 60)
    print("Adding test downloads...")
    print("=" * 60)

    from database.manager import DatabaseManager
    db = DatabaseManager(str(TEST_DB))

    for name, url in TEST_URLS.items():
        download_id = db.add_to_queue(
            url=url,
            source=name,
            title=f"Test {name}",
            chat_id=123456789,
            message_id=1
        )
        print(f"[OK] Added {name} download (ID: {download_id})")

    db.close()
    print()


def test_url_detection():
    """Test URL detection for all types."""
    print("=" * 60)
    print("Testing URL Detection...")
    print("=" * 60)

    from src.download_module.url_detector import get_url_detector

    detector = get_url_detector()

    for name, url in TEST_URLS.items():
        result = detector.detect(url)
        print(f"{name:12} -> Type: {result['type']:12} URL: {url[:60]}...")

    print("[OK] URL Detection tests completed")
    print()


async def test_extractors():
    """Test all extractors."""
    print("=" * 60)
    print("Testing URL Extractors...")
    print("=" * 60)

    from src.download_module.extractors.torrent_extractor import TorrentExtractor
    from src.download_module.extractors.ytdlp_extractor import YtdlpExtractor
    from src.download_module.extractors.playwright_extractor import PlaywrightExtractor
    from src.download_module.extractors.direct_extractor import DirectExtractor
    from database.manager import DatabaseManager

    db = DatabaseManager(str(TEST_DB))

    # Test Torrent Extractor
    print("Testing Torrent Extractor...")
    try:
        extractor = TorrentExtractor(db)
        result = await extractor.extract(TEST_URLS['torrent'], 1)
        print(f"  [OK] Torrent: {result.get('download_url', 'N/A')[:50]}...")
    except Exception as e:
        print(f"  [FAIL] Torrent: {e}")

    # Test yt-dlp Extractor
    print("Testing yt-dlp Extractor...")
    try:
        extractor = YtdlpExtractor(db)
        result = await extractor.extract(TEST_URLS['youtube'], 2)
        print(f"  [OK] yt-dlp: {result.get('title', 'N/A')}")
        print(f"  [OK] Direct URL: {result.get('download_url', 'N/A')[:50]}...")
    except Exception as e:
        print(f"  [FAIL] yt-dlp: {e}")

    # Test Direct Extractor
    print("Testing Direct Extractor...")
    try:
        extractor = DirectExtractor(db)
        result = await extractor.extract(TEST_URLS['direct'], 3)
        print(f"  [OK] Direct: File size: {result.get('file_size', 'N/A')} bytes")
    except Exception as e:
        print(f"  [FAIL] Direct: {e}")

    # Test Playwright Extractor
    print("Testing Playwright Extractor...")
    try:
        extractor = PlaywrightExtractor(db)
        # Use dummy chat_id for testing (browser context isolation)
        result = await extractor.extract(TEST_URLS['crawler'], 1)
        print(f"  [OK] Playwright: {result.get('title', 'N/A')}")
        print(f"  [OK] Direct URL: {result.get('download_url', 'N/A')[:50]}...")
    except Exception as e:
        print(f"  [FAIL] Playwright: {e}")

    print("[OK] Extractor tests completed")
    print()


async def test_aria2c_downloader():
    """Test aria2c downloader with direct URL."""
    print("=" * 60)
    print("Testing aria2c Downloader (Direct URL)...")
    print("=" * 60)

    from src.download_module.aria2c_downloader import Aria2cDownloader
    from database.manager import DatabaseManager
    import src.config

    db = DatabaseManager(str(TEST_DB))

    # Get direct download
    downloads = db.get_all_downloads(status='pending')
    direct_download = None
    for d in downloads:
        if d['url'] == TEST_URLS['direct']:
            direct_download = d
            break

    if not direct_download:
        print("[FAIL] Direct download not found in database")
        return

    try:
        downloader = Aria2cDownloader(
            db=db,
            rpc_url=src.config.ARIA2C_RPC_URL,
            download_dir='./test_downloads',
            rpc_secret=src.config.ARIA2C_RPC_SECRET
        )

        # Start download (this will block until complete)
        print(f"Starting download: {direct_download['url']}")
        print("Note: This test will download the full 20MB file...")
        output_path = await downloader.download(
            url=direct_download['url'],
            filename='20MB.zip',
            download_id=3,
            headers={}
        )
        print(f"[OK] Download completed: {output_path}")

        # Verify file exists
        import os
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"[OK] File verified: {file_size} bytes")
        else:
            print(f"[FAIL] File not found: {output_path}")

    except Exception as e:
        print(f"[FAIL] aria2c test failed: {e}")
        import traceback
        traceback.print_exc()

    db.close()
    print()


def test_cancel_manager():
    """Test cancel manager functionality."""
    print("=" * 60)
    print("Testing Cancel Manager...")
    print("=" * 60)

    from src.download_module.utils.cancel_manager import CancelManager
    from database.manager import DatabaseManager

    db = DatabaseManager(str(TEST_DB))

    # Get a download
    downloads = db.get_all_downloads(status='pending')
    if not downloads:
        print("[FAIL] No downloads found to test cancel")
        return

    download = downloads[0]
    print(f"Testing cancel on download ID: {download['id']}")

    try:
        # Test check_and_handle_cancel (should not cancel)
        should_cancel = CancelManager.check_and_handle_cancel(download['id'], db)
        print(f"  Check cancel (not cancelled): {should_cancel}")
        assert not should_cancel, "Should not cancel when cancelled=0"

        # Mark as cancelled
        db.mark_cancelled(download['id'])
        print(f"  Marked download {download['id']} as cancelled")

        # Test check_and_handle_cancel (should cancel now)
        should_cancel = CancelManager.check_and_handle_cancel(download['id'], db)
        print(f"  Check cancel (cancelled): {should_cancel}")
        assert should_cancel, "Should cancel when cancelled=1"

        print("[OK] Cancel manager tests passed")

    except Exception as e:
        print(f"[FAIL] Cancel manager test failed: {e}")
        import traceback
        traceback.print_exc()

    db.close()
    print()


async def test_full_download():
    """Test full end-to-end download from abxxx.com."""
    print("=" * 60)
    print("Full Download Test (abxxx.com)")
    print("=" * 60)
    print()

    from database.manager import DatabaseManager
    import os

    db = DatabaseManager(str(TEST_DB))

    # Add crawler download
    url = 'https://abbdsm.com/video/138079/fireworks-bondage-rim-jobs-and-gagging-on-cock-a-lovely-weekend-in-nyc/'
    download_id = db.add_to_queue(
        url=url,
        source='test',
        chat_id=123456789  # Dummy chat_id for Playwright
    )
    print(f"Added download ID: {download_id}")

    try:
        from src.download_module.download_pooler import DownloadPooler
        import src.config

        # Create pooler
        pooler = DownloadPooler(
            db=db,
            download_dir='./test_downloads',
            aria2c_rpc_url=src.config.ARIA2C_RPC_URL,
            aria2c_rpc_secret=src.config.ARIA2C_RPC_SECRET
        )

        # Process one download
        print(f"Processing download {download_id}...")
        download = db.get_download(download_id)
        await pooler._process_download(download)

        # Check result
        download = db.get_download(download_id)
        print(f"Final status: {download['status']}")
        print(f"File path: {download.get('file_path', 'N/A')}")

        # Verify file exists
        if download.get('file_path') and os.path.exists(download['file_path']):
            file_size = os.path.getsize(download['file_path'])
            print(f"[OK] File downloaded: {file_size} bytes")
        else:
            print("[FAIL] File not found")

    except Exception as e:
        print(f"[FAIL] Full download test failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()
        print()


async def run_all_tests():
    """Run all tests."""
    print("\n")
    print("=" * 60)
    print("DOWNLOAD MODULE TESTS")
    print("=" * 60)
    print()

    # Step 1: Create test database
    create_test_database()

    # Step 2: Add test downloads
    add_test_downloads()

    # Step 3: Test URL detection
    test_url_detection()

    # Step 3.5: Test full download
    await test_full_download()

    # Step 4: Test extractors
    await test_extractors()

    # Step 5: Test aria2c downloader
    await test_aria2c_downloader()

    # Step 6: Test cancel manager
    test_cancel_manager()

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("[OK] All tests completed!")
    print()
    print(f"Test database: {TEST_DB}")
    print(f"To view data: python -c \"from database.manager import DatabaseManager; db = DatabaseManager('{TEST_DB}'); print(db.get_all_downloads())\"")
    print()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
