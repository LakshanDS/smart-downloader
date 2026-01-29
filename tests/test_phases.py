#!/usr/bin/env python3
"""
Test Script for Phase 1 (Database) and Phase 2 (Bot Framework)

This script tests all features implemented in Phase 1 and Phase 2 of Smart Downloader.

Usage:
    python test_phases.py [--verbose] [--cleanup]
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime

# Add project root to path (database package is now at root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# Add src to path for other modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager


class Colors:
    """Terminal color codes."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestRunner:
    """Test runner for Smart Downloader."""

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

    # === Phase 1 Tests ===

    def test_database_initialization(self):
        """Test database creates all tables."""
        # Check if tables exist
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            required_tables = [
                'media', 'downloads', 'categories', 'media_categories',
                'owner', 'preferences', 'activity_log', 'media_fts'
            ]

            for table in required_tables:
                assert table in tables, f"Table {table} not found"

    def test_owner_lock_initially_unlocked(self):
        """Test bot is initially unlocked."""
        assert not self.db.is_locked(), "Bot should be unlocked initially"

    def test_owner_lock_setup(self):
        """Test owner lock functionality."""
        chat_id = 123456
        user_id = 789012
        username = "testuser"

        # Set owner
        self.db.set_owner(chat_id, user_id, username)

        # Verify locked
        assert self.db.is_locked(), "Bot should be locked after setup"

        # Verify owner details
        owner = self.db.get_owner()
        assert owner is not None, "Owner should exist"
        assert owner['chat_id'] == chat_id, "Chat ID mismatch"
        assert owner['user_id'] == user_id, "User ID mismatch"
        assert owner['username'] == username, "Username mismatch"

    def test_owner_cannot_lock_twice(self):
        """Test owner cannot be set twice."""
        chat_id = 111111
        user_id = 222222

        # First lock
        self.db.set_owner(chat_id, user_id, "user1")

        # Try to lock again (should fail)
        try:
            self.db.set_owner(333333, 444444, "user2")
            assert False, "Should raise ValueError when locking twice"
        except ValueError as e:
            assert "already locked" in str(e).lower(), "Error message incorrect"

    def test_authorization_check(self):
        """Test authorization checking."""
        chat_id = 999999
        user_id = 888888

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Check authorized
        assert self.db.is_authorized(chat_id), "Owner should be authorized"

        # Check unauthorized
        assert not self.db.is_authorized(12345), "Different user should not be authorized"

    def test_add_to_queue(self):
        """Test adding items to download queue."""
        chat_id = 111111
        user_id = 222222

        # Set owner (required for preferences)
        self.db.set_owner(chat_id, user_id, "test_owner")

        url = "https://example.com/video.mp4"
        source = "direct"
        title = "Test Video"

        queue_id = self.db.add_to_queue(url, source, title)

        assert queue_id > 0, "Queue ID should be positive"

        # Verify in database
        download = self.db.get_download(queue_id)
        assert download is not None, "Download should exist"
        assert download['url'] == url, "URL mismatch"
        assert download['source'] == source, "Source mismatch"
        assert download['title'] == title, "Title mismatch"
        assert download['status'] == 'pending', "Status should be pending"

    def test_queue_fifo_ordering(self):
        """Test queue follows FIFO ordering."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Add multiple items
        id1 = self.db.add_to_queue("url1", "direct", "First")
        id2 = self.db.add_to_queue("url2", "direct", "Second")
        id3 = self.db.add_to_queue("url3", "direct", "Third")

        # Get next pending
        next_item = self.db.get_next_pending()

        assert next_item is not None, "Should have pending item"
        assert next_item['id'] == id1, "Should return first item (FIFO)"

    def test_update_download_status(self):
        """Test updating download status."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")
        queue_id = self.db.add_to_queue("url", "direct", "Test")

        # Update status
        self.db.update_download_status(queue_id, 'downloading')

        download = self.db.get_download(queue_id)
        assert download['status'] == 'downloading', "Status should be updated"

    def test_update_progress(self):
        """Test updating download progress."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")
        queue_id = self.db.add_to_queue("url", "direct", "Test")

        # Update progress
        self.db.update_progress(
            queue_id,
            progress=50,
            download_speed=5.5,
            upload_speed=0.0,
            eta_seconds=120
        )

        download = self.db.get_download(queue_id)
        assert download['progress'] == 50, "Progress should be updated"
        assert download['download_speed'] == 5.5, "Download speed should be updated"
        assert download['eta_seconds'] == 120, "ETA should be updated"

    def test_increment_retry(self):
        """Test incrementing retry count."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")
        queue_id = self.db.add_to_queue("url", "direct", "Test")

        # First retry
        count1 = self.db.increment_retry(queue_id)
        assert count1 == 1, f"First retry should be 1, got {count1}"

        # Second retry
        count2 = self.db.increment_retry(queue_id)
        assert count2 == 2, f"Second retry should be 2, got {count2}"

    def test_queue_summary(self):
        """Test queue summary statistics."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Add downloads with different statuses
        id1 = self.db.add_to_queue("url1", "direct", "Test1")
        id2 = self.db.add_to_queue("url2", "direct", "Test2")
        id3 = self.db.add_to_queue("url3", "direct", "Test3")

        # Update some statuses
        self.db.update_download_status(id1, 'downloading')
        self.db.update_download_status(id2, 'failed', error_message="Test error")

        # Get summary
        summary = self.db.get_queue_summary()

        assert summary['pending'] == 1, "Should have 1 pending"
        assert summary['downloading'] == 1, "Should have 1 downloading"
        assert summary['failed'] == 1, "Should have 1 failed"
        assert summary['uploading'] == 0, "Should have 0 uploading"

    def test_active_download(self):
        """Test getting active download."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Add and activate download
        queue_id = self.db.add_to_queue("url", "direct", "Test")
        self.db.update_download_status(queue_id, 'downloading')

        # Get active
        active = self.db.get_active_download()

        assert active is not None, "Should have active download"
        assert active['id'] == queue_id, "Active download ID should match"

    def test_mark_completed(self):
        """Test marking download as completed."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")
        queue_id = self.db.add_to_queue("url", "direct", "Test")

        # Mark completed
        self.db.mark_completed(queue_id)

        download = self.db.get_download(queue_id)
        assert download['status'] == 'completed', "Status should be completed"
        assert download['progress'] == 100, "Progress should be 100"

    def test_add_media(self):
        """Test adding media to library."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        title = "Test Movie"
        source_url = "https://example.com/movie.mp4"
        source_type = "direct"
        file_size = 1024 * 1024 * 1024  # 1GB

        media_id = self.db.add_media(title, source_url, source_type, file_size)

        assert media_id > 0, "Media ID should be positive"

        # Verify in database
        media = self.db.get_media(media_id)
        assert media is not None, "Media should exist"
        assert media['title'] == title, "Title mismatch"
        assert media['source_url'] == source_url, "Source URL mismatch"
        assert media['file_size'] == file_size, "File size mismatch"

    def test_toggle_favorite(self):
        """Test toggling favorite status."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")
        media_id = self.db.add_media("Test", "url", "direct", 1000)

        # Toggle to favorite
        is_fav1 = self.db.toggle_favorite(media_id)
        assert is_fav1 is True, "Should be favorited"

        media = self.db.get_media(media_id)
        assert media['is_favorite'] == 1, "Media should be favorited"

        # Toggle back
        is_fav2 = self.db.toggle_favorite(media_id)
        assert is_fav2 is False, "Should be unfavorited"

        media = self.db.get_media(media_id)
        assert media['is_favorite'] == 0, "Media should be unfavorited"

    def test_get_favorites(self):
        """Test getting favorites."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Add media
        id1 = self.db.add_media("Media1", "url1", "direct", 1000)
        id2 = self.db.add_media("Media2", "url2", "direct", 1000)
        id3 = self.db.add_media("Media3", "url3", "direct", 1000)

        # Favorite some
        self.db.toggle_favorite(id1)
        self.db.toggle_favorite(id3)

        # Get favorites
        favorites = self.db.get_favorites()

        assert len(favorites) == 2, "Should have 2 favorites"
        fav_ids = [f['id'] for f in favorites]
        assert id1 in fav_ids, "Media1 should be in favorites"
        assert id3 in fav_ids, "Media3 should be in favorites"
        assert id2 not in fav_ids, "Media2 should not be in favorites"

    def test_search_media(self):
        """Test full-text search."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Add media
        self.db.add_media("The Matrix", "url1", "direct", 1000)
        self.db.add_media("The Godfather", "url2", "direct", 1000)
        self.db.add_media("Pulp Fiction", "url3", "direct", 1000)

        # Search
        results = self.db.search_media("The")

        assert len(results) == 2, "Should find 2 results with 'The'"
        titles = [r['title'] for r in results]
        assert "The Matrix" in titles, "Should find 'The Matrix'"
        assert "The Godfather" in titles, "Should find 'The Godfather'"

    def test_duplicate_detection(self):
        """Test duplicate file detection."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Add media
        self.db.add_media("Media1", "url1", "direct", 1000, hash="abc123")

        # Check duplicate
        is_dup1 = self.db.check_duplicate("abc123")
        assert is_dup1 is True, "Should detect duplicate"

        is_dup2 = self.db.check_duplicate("xyz789")
        assert is_dup2 is False, "Should not detect duplicate for different hash"

    # === Category Tests (New Schema) ===

    def test_default_categories_seeded(self):
        """Test default categories are seeded."""
        categories = self.db.get_all_categories()

        assert len(categories) >= 3, "Should have at least 3 default categories"

        default_names = {"Favorites", "Watch Later", "Music"}
        cat_names = {c['name'] for c in categories}

        assert default_names.issubset(cat_names), "Should have all default categories"

    def test_create_category(self):
        """Test creating user categories."""
        cat_id = self.db.create_category("Action Movies", "🎬")

        assert cat_id > 0, "Category ID should be positive"

        # Verify in database
        categories = self.db.get_all_categories()
        assert len(categories) == 4, "Should have 4 categories (3 seeded + 1 new)"
        assert any(c['name'] == "Action Movies" for c in categories), "Should find new category"

    def test_delete_category(self):
        """Test deleting category."""
        cat_id = self.db.create_category("ToDelete", "🗑️")

        # Verify exists
        categories_before = self.db.get_all_categories()
        assert any(c['name'] == "ToDelete" for c in categories_before), "Category should exist"

        # Delete
        self.db.delete_category(cat_id)

        # Verify deleted
        categories_after = self.db.get_all_categories()
        assert not any(c['name'] == "ToDelete" for c in categories_after), "Category should be deleted"

    def test_rename_category(self):
        """Test renaming category."""
        cat_id = self.db.create_category("OldName", "📁")

        # Rename
        self.db.rename_category(cat_id, "NewName")

        # Verify renamed
        categories = self.db.get_all_categories()
        category = next((c for c in categories if c['id'] == cat_id), None)
        assert category is not None, "Category should exist"
        assert category['name'] == "NewName", "Category name should be updated"

    def test_many_to_many_relationship(self):
        """Test media can be in multiple categories."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Create categories
        cat1 = self.db.create_category("Comedy", "😂")
        cat2 = self.db.create_category("Action", "💥")

        # Add media
        media_id = self.db.add_media("Test Movie", "url", "direct", 1000, category_ids=[cat1, cat2])

        # Verify media in both categories
        cat1_media = self.db.get_media_by_category(cat1)
        cat2_media = self.db.get_media_by_category(cat2)

        assert len(cat1_media) == 1, "Category 1 should have 1 media"
        assert len(cat2_media) == 1, "Category 2 should have 1 media"
        assert cat1_media[0]['id'] == media_id, "Media should match"

    def test_add_media_to_category(self):
        """Test adding media to existing category."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        cat_id = self.db.create_category("MyCustomFavorites", "❤️")
        media_id = self.db.add_media("Test", "url", "direct", 1000)

        # Add to category
        self.db.add_media_to_category(media_id, cat_id)

        # Verify
        media_cats = self.db.get_media_categories(media_id)
        assert len(media_cats) == 1, "Media should be in 1 category"
        assert media_cats[0]['id'] == cat_id, "Category should match"

    def test_remove_media_from_category(self):
        """Test removing media from category."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        cat_id = self.db.create_category("TestCategory", "📁")
        media_id = self.db.add_media("Test", "url", "direct", 1000, category_ids=[cat_id])

        # Verify in category
        assert len(self.db.get_media_by_category(cat_id)) == 1, "Media should be in category"

        # Remove
        self.db.remove_media_from_category(media_id, cat_id)

        # Verify removed
        assert len(self.db.get_media_by_category(cat_id)) == 0, "Media should be removed from category"

    def test_get_media_categories(self):
        """Test getting all categories for a media."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        cat1 = self.db.create_category("C1", "1️⃣")
        cat2 = self.db.create_category("C2", "2️⃣")
        cat3 = self.db.create_category("C3", "3️⃣")

        media_id = self.db.add_media("Test", "url", "direct", 1000, category_ids=[cat1, cat3])

        # Get categories
        media_cats = self.db.get_media_categories(media_id)

        assert len(media_cats) == 2, "Media should be in 2 categories"
        cat_ids = [c['id'] for c in media_cats]
        assert cat1 in cat_ids, "Category 1 should be present"
        assert cat3 in cat_ids, "Category 3 should be present"
        assert cat2 not in cat_ids, "Category 2 should not be present"

    def test_delete_media(self):
        """Test deleting media from library."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")
        media_id = self.db.add_media("Test", "url", "direct", 1000)

        # Delete
        deleted = self.db.delete_media(media_id)

        assert deleted is True, "Should return True on deletion"

        # Verify deleted
        media = self.db.get_media(media_id)
        assert media is None, "Media should be deleted"

    # === Activity Log Tests ===

    def test_activity_logging(self):
        """Test activity logging."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Log activity
        self.db.log_activity(123, 456, "test_action", {"key": "value"})

        # Get log
        logs = self.db.get_activity_log(limit=1)

        assert len(logs) == 1, "Should have 1 log entry"
        assert logs[0]['action'] == "test_action", "Action should match"
        assert logs[0]['user_id'] == 123, "User ID should match"

    # === Preferences Tests ===

    def test_get_preferences(self):
        """Test getting user preferences."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        prefs = self.db.get_preferences(111111)

        assert prefs is not None, "Preferences should exist"
        assert 'auto_clear_enabled' in prefs, "Should have auto_clear_enabled"

    def test_update_preferences(self):
        """Test updating preferences."""
        chat_id = 111111
        user_id = 222222

        # Set owner
        self.db.set_owner(chat_id, user_id, "owner")

        # Update
        updated = self.db.update_preferences(
            111111,
            auto_clear_enabled=True,
            auto_clear_hours=48
        )

        assert updated is True, "Should return True on update"

        # Verify
        prefs = self.db.get_preferences(111111)
        assert prefs['auto_clear_enabled'] == 1, "auto_clear_enabled should be updated"
        assert prefs['auto_clear_hours'] == 48, "auto_clear_hours should be updated"

    def run_all(self):
        """Run all tests."""
        print(f"\n{Colors.BOLD}Smart Downloader - Phase 1 & 2 Test Suite{Colors.RESET}")
        print("=" * 60)

        # Setup
        self.setup()

        print(f"\n{Colors.BLUE}Running Phase 1 Tests (Database)...{Colors.RESET}\n")

        # Database Initialization Tests
        self.setup_db()
        self.test("Database initialization", self.test_database_initialization, reset=False)
        self.test("Database initially unlocked", self.test_owner_lock_initially_unlocked)

        # Owner Lock Tests
        self.test("Owner lock setup", self.test_owner_lock_setup)
        self.test("Owner cannot lock twice", self.test_owner_cannot_lock_twice)
        self.test("Authorization check", self.test_authorization_check)

        # Queue Tests
        self.test("Add to queue", self.test_add_to_queue)
        self.test("Queue FIFO ordering", self.test_queue_fifo_ordering)
        self.test("Update download status", self.test_update_download_status)
        self.test("Update progress", self.test_update_progress)
        self.test("Increment retry count", self.test_increment_retry)
        self.test("Queue summary", self.test_queue_summary)
        self.test("Active download", self.test_active_download)
        self.test("Mark completed", self.test_mark_completed)

        # Media Tests
        self.test("Add media", self.test_add_media)
        self.test("Toggle favorite", self.test_toggle_favorite)
        self.test("Get favorites", self.test_get_favorites)
        self.test("Search media", self.test_search_media)
        self.test("Duplicate detection", self.test_duplicate_detection)
        self.test("Delete media", self.test_delete_media)

        # Category Tests (New Schema)
        print(f"\n{Colors.BLUE}Running Category Tests (User-Created)...{Colors.RESET}\n")
        self.test("Default categories seeded", self.test_default_categories_seeded)
        self.test("Create category", self.test_create_category)
        self.test("Delete category", self.test_delete_category)
        self.test("Rename category", self.test_rename_category)
        self.test("Many-to-many relationship", self.test_many_to_many_relationship)
        self.test("Add media to category", self.test_add_media_to_category)
        self.test("Remove media from category", self.test_remove_media_from_category)
        self.test("Get media categories", self.test_get_media_categories)

        # Activity Log Tests
        print(f"\n{Colors.BLUE}Running Activity Log Tests...{Colors.RESET}\n")
        self.test("Activity logging", self.test_activity_logging)

        # Preferences Tests
        print(f"\n{Colors.BLUE}Running Preferences Tests...{Colors.RESET}\n")
        self.test("Get preferences", self.test_get_preferences)
        self.test("Update preferences", self.test_update_preferences)

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

    parser = argparse.ArgumentParser(description="Test Smart Downloader Phase 1 & 2")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--no-cleanup", action="store_true", help="Don't cleanup test database")

    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose, cleanup=not args.no_cleanup)
    success = runner.run_all()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
