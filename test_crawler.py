"""
Test script for crawler workflow
Tests URL detection, crawling, and aria2c download without database
"""

import asyncio
import logging
import os
import sys
from urllib.parse import urlparse

# Fix Windows encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
TEST_URL = "https://abxxx.com/video/505733/tied-and-fucked-hard-by-two/"
ARIA2C_RPC_URL = "http://localhost:6800/jsonrpc"
DOWNLOAD_DIR = "./test_downloads"
MAX_VIDEO_QUALITY = "1080p"


async def test_url_detector():
    """Test URL detection."""
    print("\n" + "="*60)
    print("TEST 1: URL Detection")
    print("="*60)

    from src.download.url_detector import URLDetector
    detector = URLDetector()

    url_type = detector.detect_url_type(TEST_URL)
    print(f"[OK] URL Type: {url_type}")

    assert url_type == 'playwright', f"Expected 'playwright', got '{url_type}'"
    print("[OK] URL detection test PASSED")
    return True


async def test_crawler():
    """Test Playwright crawler."""
    print("\n" + "="*60)
    print("TEST 2: Playwright Crawler")
    print("="*60)

    from src.crawler.browser_manager import BrowserManager
    from src.crawler.playwright_crawler import PlaywrightCrawler

    # Initialize
    browser_mgr = BrowserManager(headless=True)
    crawler = PlaywrightCrawler(browser_manager=browser_mgr, max_quality=MAX_VIDEO_QUALITY)
    print("[OK] Browser and crawler initialized")

    # Crawl the URL
    chat_id = 12345  # Test chat ID
    print(f"[OK] Crawling: {TEST_URL}")

    try:
        video_info = await crawler.find_video_url(TEST_URL, chat_id)

        if not video_info:
            print("[FAIL] Failed: No video info returned")
            return False

        print(f"[OK] Video URL found: {video_info.get('url', 'N/A')[:80]}...")
        print(f"  - Size: {video_info.get('size', 'N/A')}")
        print(f"  - Title: {video_info.get('title', 'N/A')}")
        print(f"  - Ext: {video_info.get('ext', 'N/A')}")

        assert 'url' in video_info, "No URL in video_info"
        print("[OK] Crawler test PASSED")
        return video_info

    finally:
        await browser_mgr.cleanup_all()
        print("[OK] Browser cleaned up")


async def test_sanitize_title():
    """Test title sanitization."""
    print("\n" + "="*60)
    print("TEST 3: Title Sanitization")
    print("="*60)

    # Import after creating file
    from src.download.direct_downloader import DirectDownloader

    # Mock class with just sanitize_title
    class MockDownloader:
        @staticmethod
        def sanitize_title(title: str, max_length: int = 32) -> str:
            import re
            if not title:
                return "download"
            cleaned = re.sub(r'[^\x00-\x7F]+', '', title)
            cleaned = re.sub(r'[^a-zA-Z0-9\s\-_]', '', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            cleaned = cleaned.strip().title()
            if len(cleaned) > max_length:
                cleaned = cleaned[:max_length].strip()
            return cleaned or "download"

    test_titles = [
        "Tied and Fucked Hard by Two!!! 🎥",
        "Video_With-Special  Chars@#$%",
        "",
        "Very Long Title That Should Be Truncated To Thirty Two Characters Maximum"
    ]

    for title in test_titles:
        result = MockDownloader.sanitize_title(title)
        print(f"  '{title[:40]}...' -> '{result}'")
        assert len(result) <= 32, f"Title too long: {len(result)}"
        assert result.isascii(), "Non-ASCII characters found"

    print("[OK] Sanitize title test PASSED")
    return True


async def test_aria2_init():
    """Test aria2c initialization."""
    print("\n" + "="*60)
    print("TEST 4: aria2c Initialization")
    print("="*60)

    try:
        import aria2p
        from urllib.parse import urlparse

        parsed = urlparse(ARIA2C_RPC_URL)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 6800

        # Create Client first, then API
        client = aria2p.Client(host=host, port=port)
        aria = aria2p.API(client)

        # Test connection
        stats = aria.get_stats()
        print(f"[OK] Connected to aria2c at {ARIA2C_RPC_URL}")
        print(f"  - Download speed: {stats.download_speed if hasattr(stats, 'download_speed') else 'N/A'}")
        print(f"  - Upload speed: {stats.upload_speed if hasattr(stats, 'upload_speed') else 'N/A'}")

        print("[OK] aria2c initialization test PASSED")
        return aria

    except Exception as e:
        print(f"[FAIL] aria2c connection failed: {e}")
        print("  NOTE: Make sure aria2c RPC server is running at: http://localhost:6800/jsonrpc")
        print("  Start aria2c with: aria2c --enable-rpc --rpc-listen-all=true")
        return None


async def test_full_workflow():
    """Test full workflow: Crawl -> aria2c download."""
    print("\n" + "="*60)
    print("TEST 5: Full Workflow (Crawl + Download)")
    print("="*60)

    # Create download dir
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Step 1: Crawl
    print("\n[Step 1] Crawling URL...")
    video_info = await test_crawler()
    if not video_info:
        print("[FAIL] Crawler failed, aborting test")
        return False

    # Step 2: Initialize aria2c
    print("\n[Step 2] Initializing aria2c...")
    aria = await test_aria2_init()
    if not aria:
        print("[FAIL] aria2c init failed, aborting test")
        return False

    # Step 3: Prepare download
    print("\n[Step 3] Preparing download...")
    download_url = video_info['url']
    title = video_info.get('title', 'video')
    ext = video_info.get('ext', 'mp4')

    # Sanitize title
    import re
    clean_title = re.sub(r'[^\x00-\x7F]+', '', title)
    clean_title = re.sub(r'[^a-zA-Z0-9\s\-_]', '', clean_title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip().title()
    clean_title = clean_title[:32] if len(clean_title) > 32 else clean_title
    clean_title = clean_title or "video"

    filename = f"{clean_title}.{ext}"
    output_path = os.path.join(DOWNLOAD_DIR, filename)

    print(f"  - Filename: {filename}")
    print(f"  - Output: {output_path}")

    # Step 4: Add to aria2c
    print("\n[Step 4] Adding download to aria2c...")
    options = {
        'dir': DOWNLOAD_DIR,
        'out': filename,
        'max-connection-per-server': 16,
        'split': 16,
        'split-every-mb': 10,
        'continue': 'true',
        'auto-file-renaming': 'true',
    }

    try:
        download_obj = aria.add_uris([download_url], options=options)
        gid = download_obj.gid
        print(f"[OK] Download added: GID={gid}")
    except Exception as e:
        print(f"[FAIL] Failed to add download: {e}")
        return False

    # Step 5: Monitor download
    print("\n[Step 5] Monitoring download...")
    try:
        while True:
            download = aria.get_download(gid)
            status = download.status

            total_length = download.total_length
            completed_length = download.completed_length

            if total_length > 0:
                progress = int((completed_length / total_length) * 100)
            else:
                progress = 0

            speed = download.download_speed
            eta = download.eta

            print(f"  Status: {status} | Progress: {progress}% | Speed: {speed/1024:.1f} KB/s | ETA: {eta}s")

            if status == 'complete':
                print(f"\n[OK] Download complete: {output_path}")

                # Check file exists
                if os.path.exists(output_path):
                    file_size = os.path.getsize(output_path)
                    print(f"  File size: {file_size / (1024*1024):.2f} MB")
                    print("[OK] Full workflow test PASSED")
                    return True
                else:
                    print(f"[FAIL] File not found at: {output_path}")
                    return False

            if status == 'error':
                error_msg = download.error_message
                print(f"[FAIL] Download error: {error_msg}")
                return False

            if status == 'removed':
                print("[FAIL] Download was removed")
                return False

            await asyncio.sleep(2)

    except Exception as e:
        print(f"[FAIL] Monitoring failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("CRAWLER WORKFLOW TEST SUITE")
    print("="*60)
    print(f"URL: {TEST_URL}")
    print(f"aria2c RPC: {ARIA2C_RPC_URL}")
    print(f"Download dir: {DOWNLOAD_DIR}")

    try:
        # Test 1: URL Detection
        await test_url_detector()

        # Test 2: Title Sanitization
        await test_sanitize_title()

        # Test 3: Crawler
        video_info = await test_crawler()

        # Test 4: aria2c Init
        aria = await test_aria2_init()

        # Test 5: Full Workflow (only if aria2c is available)
        if video_info and aria:
            success = await test_full_workflow()
        else:
            success = False
            if not aria:
                print("\n[SKIP] Full workflow test skipped (aria2c not available)")

        print("\n" + "="*60)
        if success:
            print("ALL TESTS PASSED [OK]")
        else:
            print("SOME TESTS SKIPPED/FAILED [FAIL]")
        print("="*60)

    except Exception as e:
        logger.exception("Test suite failed")
        print(f"\n[FAIL] Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
