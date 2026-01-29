#!/usr/bin/env python3
"""
Test Script for Phase 5 (Direct Download Handler) and Phase 6 (Playwright Crawler)

This script tests all features implemented in Phase 5 and Phase 6 of Smart Downloader.

Usage:
    python test_phase56.py [--verbose] [--cleanup]
"""

import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, AsyncMock

# Add project root to path (database package is now at root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# Add src to path for other modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager
from direct_handler import DirectHandler, DirectHTTPHandler


class Colors:
    """Terminal color codes."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestRunner:
    """Test runner for Smart Downloader Phases 5 & 6."""

    def __init__(self, verbose=False, cleanup=True):
        self.verbose = verbose
        self.cleanup = cleanup
        self.test_dir = None
        self.test_db = None
        self.passed = 0
        self.failed = 0

    def setup(self):
        """Setup test environment."""
        # Create temporary directory
        self.test_dir = tempfile.mkdtemp(prefix='smartdownloader_test_')
        self.test_db = os.path.join(self.test_dir, 'test.db')

        if self.verbose:
            print(f"\n{Colors.BLUE}Setup: Using test database at {self.test_db}{Colors.RESET}")

    def setup_db(self):
        """Create fresh database instance."""
        self.db = DatabaseManager(self.test_db)

    def reset_db(self):
        """Reset database for fresh test."""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.setup_db()

    def teardown(self):
        """Cleanup test environment."""
        if self.cleanup and self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            if self.verbose:
                print(f"\n{Colors.BLUE}Teardown: Cleaned up {self.test_dir}{Colors.RESET}")

    def test(self, name, func, reset=True):
        """Run a single test."""
        if reset:
            self.reset_db()

        try:
            func()
            self.passed += 1
            if self.verbose:
                print(f"{Colors.GREEN}✓{Colors.RESET} {name}")
        except AssertionError as e:
            self.failed += 1
            print(f"{Colors.RED}✗{Colors.RESET} {name}")
            if self.verbose:
                print(f"  {Colors.RED}Error: {e}{Colors.RESET}")
        except Exception as e:
            self.failed += 1
            print(f"{Colors.RED}✗{Colors.RESET} {name}")
            print(f"  {Colors.RED}Unexpected error: {e}{Colors.RESET}")

    # === Phase 5: Direct Handler Tests ===

    def test_direct_handler_initialization(self):
        """Test direct handler initializes correctly."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        handler = DirectHandler(db=self.db, download_dir=self.test_dir)

        assert handler.db is not None, "Database should be set"
        assert handler.download_dir is not None, "Download dir should be set"
        assert hasattr(handler, 'MAX_FILE_SIZE'), "Should have MAX_FILE_SIZE"

    def test_max_file_size_constant(self):
        """Test MAX_FILE_SIZE is 2GB."""
        assert DirectHandler.MAX_FILE_SIZE == 2 * 1024 * 1024 * 1024, \
            "MAX_FILE_SIZE should be 2GB"

    def test_validate_file_size_valid(self):
        """Test file size validation for valid files."""
        handler = DirectHandler(db=None)

        # Valid file under 2GB
        metadata = {'filesize': 1024 * 1024 * 1024}  # 1GB
        assert handler.validate_file_size(metadata) is True, "Should accept files under 2GB"

    def test_validate_file_size_invalid(self):
        """Test file size validation for oversized files."""
        handler = DirectHandler(db=None)

        # Invalid file over 2GB
        metadata = {'filesize': 3 * 1024 * 1024 * 1024}  # 3GB
        assert handler.validate_file_size(metadata) is False, "Should reject files over 2GB"

    def test_validate_file_size_unknown(self):
        """Test file size validation when size is unknown."""
        handler = DirectHandler(db=None)

        # Unknown size (should allow but warn)
        metadata = {'filesize': None}
        assert handler.validate_file_size(metadata) is True, "Should allow unknown sizes"

    def test_direct_http_handler_initialization(self):
        """Test HTTP handler initializes correctly."""
        self.setup_db()

        handler = DirectHTTPHandler(db=self.db, download_dir=self.test_dir)

        assert handler.db is not None, "Database should be set"
        assert handler.download_dir is not None, "Download dir should be set"
        assert hasattr(handler, 'MAX_FILE_SIZE'), "Should have MAX_FILE_SIZE"

    def test_download_error_exception(self):
        """Test DownloadError exception exists."""
        from direct_handler import DownloadError

        try:
            raise DownloadError("Test error")
        except DownloadError as e:
            assert str(e) == "Test error", "Exception message should match"

    # === Phase 6: Playwright Crawler Tests ===

    def test_browser_manager_initialization(self):
        """Test browser manager initializes correctly."""
        from browser_manager import BrowserManager

        bm = BrowserManager(headless=True)

        assert bm.browser is None, "Browser should not be initialized yet"
        assert bm.contexts == {}, "Contexts should be empty"
        assert bm.headless is True, "Headless flag should be set"

    def test_browser_manager_cleanup_all(self):
        """Test browser cleanup works without errors."""
        from browser_manager import BrowserManager

        bm = BrowserManager(headless=True)
        # Cleanup without initializing should not crash
        bm.cleanup_all()

    def test_video_detector_initialization(self):
        """Test video detector initializes correctly."""
        from video_detector import VideoDetector

        detector = VideoDetector()

        assert hasattr(detector, 'ad_keywords'), "Should have ad keywords"
        assert hasattr(detector, 'min_duration'), "Should have min duration"
        assert hasattr(detector, 'min_size'), "Should have min size"

    def test_video_detector_filter_empty(self):
        """Test video detector returns None for empty candidates."""
        from video_detector import VideoDetector

        detector = VideoDetector()
        result = detector.filter_videos([])

        assert result is None, "Should return None for empty candidates"

    def test_video_detector_is_video_valid(self):
        """Test video detection for valid video content types."""
        from video_detector import VideoDetector

        detector = VideoDetector()

        # Valid video types
        valid_types = [
            {'content-type': 'video/mp4', 'url': 'http://example.com/video.mp4'},
            {'content-type': 'video/webm', 'url': 'http://example.com/video.webm'},
            {'content-type': 'video/ogg', 'url': 'http://example.com/video.ogg'},
        ]

        for candidate in valid_types:
            assert detector._is_video(candidate) is True, \
                f"Should detect {candidate['content-type']} as video"

    def test_video_detector_is_video_invalid(self):
        """Test video detection rejects non-video content types."""
        from video_detector import VideoDetector

        detector = VideoDetector()

        # Invalid types
        invalid_types = [
            {'content-type': 'text/html', 'url': 'http://example.com/page.html'},
            {'content-type': 'application/json', 'url': 'http://example.com/data.json'},
            {'content-type': 'image/jpeg', 'url': 'http://example.com/image.jpg'},
        ]

        for candidate in invalid_types:
            assert detector._is_video(candidate) is False, \
                f"Should reject {candidate['content-type']} as video"

    def test_video_detector_is_likely_ad_url(self):
        """Test ad detection based on URL keywords."""
        from video_detector import VideoDetector

        detector = VideoDetector()

        # Ad URLs
        ad_candidates = [
            {'url': 'http://example.com/advertisement.mp4'},
            {'url': 'http://example.com/promo_video.mp4'},
            {'url': 'http://example.com/commercial.mp4'},
        ]

        for candidate in ad_candidates:
            assert detector._is_likely_ad(candidate) is True, \
                f"Should detect {candidate['url']} as ad"

    def test_video_detector_is_likely_ad_size(self):
        """Test ad detection based on file size."""
        from video_detector import VideoDetector

        detector = VideoDetector()

        # Too small (likely ad)
        small_candidate = {
            'url': 'http://example.com/video.mp4',
            'size': 100 * 1024  # 100KB
        }

        assert detector._is_likely_ad(small_candidate) is True, \
            "Should detect tiny files as ads"

    def test_network_monitor_initialization(self):
        """Test network monitor initializes correctly."""
        from network_monitor import NetworkMonitor

        monitor = NetworkMonitor()

        assert monitor.video_urls == set(), "Video URLs should be empty"
        assert monitor.candidates == [], "Candidates should be empty"

    def test_network_monitor_reset(self):
        """Test network monitor reset works."""
        from network_monitor import NetworkMonitor

        monitor = NetworkMonitor()

        # Add some fake data
        monitor.video_urls.add('http://example.com/video1.mp4')
        monitor.candidates.append({'url': 'http://example.com/video2.mp4'})

        # Reset
        monitor.reset()

        assert monitor.video_urls == set(), "Should reset video URLs"
        assert monitor.candidates == [], "Should reset candidates"

    def test_network_monitor_get_candidates(self):
        """Test getting candidates from monitor."""
        from network_monitor import NetworkMonitor

        monitor = NetworkMonitor()

        # Add candidates
        monitor.candidates.append({'url': 'http://example.com/video1.mp4'})
        monitor.candidates.append({'url': 'http://example.com/video2.mp4'})

        candidates = monitor.get_candidates()

        assert len(candidates) == 2, "Should return 2 candidates"
        assert len(monitor.candidates) == 2, "Should not modify original list"

    def test_network_monitor_get_unique_urls(self):
        """Test getting unique URLs from monitor."""
        from network_monitor import NetworkMonitor

        monitor = NetworkMonitor()

        # Add URLs (including duplicates)
        monitor.video_urls.add('http://example.com/video.mp4')
        monitor.video_urls.add('http://example.com/video.mp4')  # Duplicate
        monitor.video_urls.add('http://example.com/other.mp4')

        urls = monitor.get_unique_urls()

        assert len(urls) == 2, "Should return 2 unique URLs"
        assert 'http://example.com/video.mp4' in urls, "Should contain video URL"

    def test_playwright_crawler_initialization(self):
        """Test playwright crawler initializes correctly."""
        from playwright_crawler import PlaywrightCrawler
        from browser_manager import BrowserManager

        bm = BrowserManager(headless=True)
        crawler = PlaywrightCrawler(browser_manager=bm)

        assert crawler.browser is not None, "Browser manager should be set"
        assert crawler.detector is not None, "Detector should be set"
        assert crawler.monitor is not None, "Monitor should be set"

    def test_playwright_crawler_download_error(self):
        """Test DownloadError exception exists in crawler."""
        from playwright_crawler import DownloadError

        try:
            raise DownloadError("Test error")
        except DownloadError as e:
            assert str(e) == "Test error", "Exception message should match"

    def test_constants_definition(self):
        """Test that all constants are properly defined."""
        from config import (
            MAX_FILE_SIZE, DOWNLOAD_DIR, BROWSER_HEADLESS,
            BROWSER_TIMEOUT, YTDLP_FORMAT
        )

        assert MAX_FILE_SIZE == 2 * 1024 * 1024 * 1024, "MAX_FILE_SIZE should be 2GB"
        assert DOWNLOAD_DIR is not None, "DOWNLOAD_DIR should be set"
        assert isinstance(BROWSER_HEADLESS, bool), "BROWSER_HEADLESS should be boolean"
        assert isinstance(BROWSER_TIMEOUT, int), "BROWSER_TIMEOUT should be integer"
        assert YTDLP_FORMAT is not None, "YTDLP_FORMAT should be set"

    def run_all(self):
        """Run all tests."""
        print(f"\n{Colors.BOLD}Smart Downloader - Phase 5 & 6 Test Suite{Colors.RESET}")
        print("=" * 60)

        # Setup
        self.setup()

        print(f"\n{Colors.BLUE}Running Phase 5 Tests (Direct Download Handler)...{Colors.RESET}\n")

        # Phase 5 Tests
        self.setup_db()
        self.test("Direct handler initialization", self.test_direct_handler_initialization, reset=False)
        self.test("MAX_FILE_SIZE constant", self.test_max_file_size_constant)
        self.test("Validate file size (valid)", self.test_validate_file_size_valid)
        self.test("Validate file size (invalid)", self.test_validate_file_size_invalid)
        self.test("Validate file size (unknown)", self.test_validate_file_size_unknown)
        self.test("Direct HTTP handler initialization", self.test_direct_http_handler_initialization)
        self.test("DownloadError exception", self.test_download_error_exception)

        # Phase 6 Tests
        print(f"\n{Colors.BLUE}Running Phase 6 Tests (Playwright Crawler)...{Colors.RESET}\n")
        self.test("Browser manager initialization", self.test_browser_manager_initialization)
        self.test("Browser manager cleanup", self.test_browser_manager_cleanup_all)
        self.test("Video detector initialization", self.test_video_detector_initialization)
        self.test("Video detector filter empty", self.test_video_detector_filter_empty)
        self.test("Video detector is_video (valid)", self.test_video_detector_is_video_valid)
        self.test("Video detector is_video (invalid)", self.test_video_detector_is_video_invalid)
        self.test("Video detector is_likely_ad (URL)", self.test_video_detector_is_likely_ad_url)
        self.test("Video detector is_likely_ad (size)", self.test_video_detector_is_likely_ad_size)
        self.test("Network monitor initialization", self.test_network_monitor_initialization)
        self.test("Network monitor reset", self.test_network_monitor_reset)
        self.test("Network monitor get candidates", self.test_network_monitor_get_candidates)
        self.test("Network monitor get unique URLs", self.test_network_monitor_get_unique_urls)
        self.test("Playwright crawler initialization", self.test_playwright_crawler_initialization)
        self.test("Playwright crawler DownloadError", self.test_playwright_crawler_download_error)
        self.test("Constants definition", self.test_constants_definition)

        # Teardown
        self.teardown()

        # Summary
        print("\n" + "=" * 60)
        print(f"{Colors.BOLD}Test Results:{Colors.RESET}")
        print(f"  {Colors.GREEN}Passed: {self.passed}{Colors.RESET}")
        print(f"  {Colors.RED}Failed: {self.failed}{Colors.RESET}")
        print(f"  {Colors.BOLD}Total:  {self.passed + self.failed}{Colors.RESET}")
        print("=" * 60)

        return self.failed == 0


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Smart Downloader Phase 5 & 6")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--no-cleanup", action="store_true", help="Don't cleanup test database")

    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose, cleanup=not args.no_cleanup)
    success = runner.run_all()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
