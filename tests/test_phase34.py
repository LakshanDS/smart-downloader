#!/usr/bin/env python3
"""
Test Script for Phase 3 (Queue Manager) and Phase 4 (Torrent Handler)

This script tests all features implemented in Phase 3 and Phase 4 of Smart Downloader.

Usage:
    python test_phase34.py [--verbose] [--cleanup]
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, AsyncMock

# Add project root to path (database package is now at root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# Add src to path for other modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager
from queue_manager import QueueManager
from torrent_manager import TorrentManager, InvalidURLError, DownloadError


class Colors:
    """Terminal color codes."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestRunner:
    """Test runner for Smart Downloader Phases 3 & 4."""

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

    # === Phase 3: Queue Manager Tests ===

    def test_queue_manager_initialization(self):
        """Test queue manager initializes correctly."""
        self.setup_db()
        # Set up owner
        self.db.set_owner(111111, 222222, "test_owner")

        mock_bot = Mock()
        qm = QueueManager(db=self.db, bot=mock_bot)

        assert qm.db is not None, "Database should be set"
        assert qm.bot is not None, "Bot should be set"
        assert qm.running is False, "Should not be running initially"

    def test_add_to_queue_basic(self):
        """Test adding item to queue."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        mock_bot = Mock()
        qm = QueueManager(db=self.db, bot=mock_bot)

        import asyncio
        queue_id = asyncio.run(qm.add_to_queue(
            url="https://example.com/video.mp4",
            source="direct",
            chat_id=111111,
            title="Test Video"
        ))

        assert queue_id > 0, "Queue ID should be positive"

        download = self.db.get_download(queue_id)
        assert download is not None, "Download should exist"
        assert download['source'] == 'direct', "Source should match"
        assert download['status'] == 'pending', "Status should be pending"

    def test_file_size_validation_too_large(self):
        """Test oversized file is rejected."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        # Create mock bot with async send_message
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock(return_value=Mock(message_id=999))

        qm = QueueManager(db=self.db, bot=mock_bot)

        import asyncio
        # File larger than 2GB
        oversized_size = 3 * 1024 * 1024 * 1024  # 3GB

        queue_id = asyncio.run(qm.add_to_queue(
            url="https://example.com/huge.mp4",
            source="direct",
            chat_id=111111,
            title="Huge Video",
            file_size=oversized_size
        ))

        assert queue_id == -1, "Should return -1 for oversized files"

        # Should have called send_message for notification
        mock_bot.send_message.assert_called()

        # Download should be in DB and marked as failed
        # The actual queue_id is stored in DB, but -1 is returned
        downloads = self.db.get_all_downloads()
        assert len(downloads) > 0, "Download should exist in DB"
        download = downloads[-1]  # Get the last added download
        assert download['status'] == 'failed', "Should be marked as failed"
        assert 'too large' in download['error_message'].lower(), "Error message should mention file size"

    def test_file_size_validation_acceptable(self):
        """Test acceptable file size passes validation."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        mock_bot = Mock()
        qm = QueueManager(db=self.db, bot=mock_bot)

        import asyncio
        # File under 2GB
        normal_size = 1024 * 1024 * 1024  # 1GB

        queue_id = asyncio.run(qm.add_to_queue(
            url="https://example.com/normal.mp4",
            source="direct",
            chat_id=111111,
            title="Normal Video",
            file_size=normal_size
        ))

        assert queue_id > 0, "Should accept files under 2GB"

        download = self.db.get_download(queue_id)
        assert download['status'] == 'pending', "Status should be pending (not failed)"

    def test_update_progress(self):
        """Test updating download progress."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        mock_bot = Mock()
        qm = QueueManager(db=self.db, bot=mock_bot)

        # Add download first
        import asyncio
        queue_id = asyncio.run(qm.add_to_queue(
            url="https://example.com/video.mp4",
            source="direct",
            chat_id=111111
        ))

        # Update progress
        asyncio.run(qm.update_progress(
            queue_id,
            progress=50,
            download_speed=5.5,
            upload_speed=0.0,
            eta_seconds=120
        ))

        download = self.db.get_download(queue_id)
        assert download['progress'] == 50, "Progress should be updated"
        assert download['download_speed'] == 5.5, "Download speed should be updated"

    def test_mark_completed(self):
        """Test marking download as completed."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        mock_bot = Mock()
        qm = QueueManager(db=self.db, bot=mock_bot)

        # Add download
        import asyncio
        queue_id = asyncio.run(qm.add_to_queue(
            url="https://example.com/video.mp4",
            source="direct",
            chat_id=111111
        ))

        # Mark as completed
        asyncio.run(qm.mark_completed(queue_id))

        download = self.db.get_download(queue_id)
        assert download['status'] == 'completed', "Status should be completed"

    def test_mark_failed(self):
        """Test marking download as failed."""
        self.setup_db()
        self.db.set_owner(111111, 222222, "test_owner")

        mock_bot = Mock()
        qm = QueueManager(db=self.db, bot=mock_bot)

        # Add download
        import asyncio
        queue_id = asyncio.run(qm.add_to_queue(
            url="https://example.com/video.mp4",
            source="direct",
            chat_id=111111
        ))

        # Mark as failed
        error_msg = "Network error"
        asyncio.run(qm.mark_failed(queue_id, error_msg))

        download = self.db.get_download(queue_id)
        assert download['status'] == 'failed', "Status should be failed"
        assert download['error_message'] == error_msg, "Error message should be set"

    # === Phase 4: Torrent Manager Tests ===

    def test_torrent_manager_initialization(self):
        """Test torrent manager initializes."""
        self.setup_db()

        tm = TorrentManager(db=self.db, rpc_url="http://localhost:6800/jsonrpc")

        assert tm.db is not None, "Database should be set"
        assert tm.rpc_url is not None, "RPC URL should be set"
        # aria2p might not be installed, so aria could be None
        # That's OK for this test

    def test_magnet_link_parsing(self):
        """Test parsing magnet links."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        magnet = "magnet:?xt=urn:btih:1234567890abcdef&dn=Test+Torrent&tr=http://tracker.example.com"

        info = tm._parse_magnet(magnet)

        assert info['name'] == 'Test Torrent', "Should parse display name"
        assert info['xt'] == 'urn:btih:1234567890abcdef', "Should parse xt parameter"
        assert len(info['trackers']) > 0, "Should parse trackers"
        assert info['size'] == 0, "Size should be unknown from magnet alone"

    def test_invalid_magnet_link(self):
        """Test invalid magnet link detection."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        # Test various invalid formats
        invalid_links = [
            "https://example.com/torrent",
            "magnet:invalid",
            "http://magnet:?xt=...",
            ""
        ]

        for link in invalid_links:
            try:
                tm.download_magnet(link)
                assert False, f"Should reject invalid link: {link[:30]}..."
            except (InvalidURLError, DownloadError):
                pass  # Expected

    def test_get_status_without_aria2c(self):
        """Test get_status handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        # Without aria2c running, should return error status
        status = tm.get_status("test_gid")

        assert status['status'] == 'error', "Should return error status"
        assert status['progress'] == 0, "Progress should be 0"
        assert status['gid'] == 'test_gid', "GID should be preserved"

    def test_pause_download_without_aria2c(self):
        """Test pause_download handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        result = tm.pause_download("test_gid")
        assert result is False, "Should return False without aria2c"

    def test_remove_download_without_aria2c(self):
        """Test remove_download handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        result = tm.remove_download("test_gid")
        assert result is False, "Should return False without aria2c"

    def test_get_active_downloads_without_aria2c(self):
        """Test get_active_downloads handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        active = tm.get_active_downloads()
        assert active == [], "Should return empty list without aria2c"

    def test_get_waiting_downloads_without_aria2c(self):
        """Test get_waiting_downloads handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        waiting = tm.get_waiting_downloads()
        assert waiting == [], "Should return empty list without aria2c"

    def test_get_global_stats_without_aria2c(self):
        """Test get_global_stats handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        stats = tm.get_global_stats()
        assert stats == {}, "Should return empty dict without aria2c"

    def test_check_connection_without_aria2c(self):
        """Test check_connection handles missing aria2c gracefully."""
        self.setup_db()
        tm = TorrentManager(db=self.db)

        result = tm.check_connection()
        assert result is False, "Should return False without aria2c"

    def test_constants(self):
        """Test that constants are properly defined."""
        # Queue Manager constants
        from queue_manager import QueueManager
        assert hasattr(QueueManager, 'MAX_FILE_SIZE'), "Should have MAX_FILE_SIZE"
        assert hasattr(QueueManager, 'RETRY_DELAYS'), "Should have RETRY_DELAYS"
        assert hasattr(QueueManager, 'PROGRESS_INTERVAL'), "Should have PROGRESS_INTERVAL"

        # Verify values
        assert QueueManager.MAX_FILE_SIZE == 2 * 1024 * 1024 * 1024, "Max file size should be 2GB"
        assert QueueManager.RETRY_DELAYS == [0, 120, 480], "Retry delays should match"

    def run_all(self):
        """Run all tests."""
        print(f"\n{Colors.BOLD}Smart Downloader - Phase 3 & 4 Test Suite{Colors.RESET}")
        print("=" * 60)

        # Setup
        self.setup()

        print(f"\n{Colors.BLUE}Running Phase 3 Tests (Queue Manager)...{Colors.RESET}\n")

        # Phase 3 Tests
        self.setup_db()
        self.test("Queue manager initialization", self.test_queue_manager_initialization, reset=False)
        self.test("Add to queue (basic)", self.test_add_to_queue_basic)
        self.test("File size validation (too large)", self.test_file_size_validation_too_large)
        self.test("File size validation (acceptable)", self.test_file_size_validation_acceptable)
        self.test("Update progress", self.test_update_progress)
        self.test("Mark completed", self.test_mark_completed)
        self.test("Mark failed", self.test_mark_failed)

        # Phase 4 Tests
        print(f"\n{Colors.BLUE}Running Phase 4 Tests (Torrent Manager)...{Colors.RESET}\n")
        self.test("Torrent manager initialization", self.test_torrent_manager_initialization)
        self.test("Magnet link parsing", self.test_magnet_link_parsing)
        self.test("Invalid magnet link detection", self.test_invalid_magnet_link)
        self.test("Get status without aria2c", self.test_get_status_without_aria2c)
        self.test("Pause download without aria2c", self.test_pause_download_without_aria2c)
        self.test("Remove download without aria2c", self.test_remove_download_without_aria2c)
        self.test("Get active downloads without aria2c", self.test_get_active_downloads_without_aria2c)
        self.test("Get waiting downloads without aria2c", self.test_get_waiting_downloads_without_aria2c)
        self.test("Get global stats without aria2c", self.test_get_global_stats_without_aria2c)
        self.test("Check connection without aria2c", self.test_check_connection_without_aria2c)
        self.test("Constants validation", self.test_constants)

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

    parser = argparse.ArgumentParser(description="Test Smart Downloader Phase 3 & 4")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--no-cleanup", action="store_true", help="Don't cleanup test database")

    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose, cleanup=not args.no_cleanup)
    success = runner.run_all()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
