"""
Database Module Tests - Phase 1

Run: python -m pytest tests/test_database.py
Or: python tests/test_database.py
"""

import os
import sys
import sqlite3
import io

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add project root to path (database package is now at root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database import DatabaseManager


def test_database_initialization():
    """Test that database is created with all tables."""
    print("Testing database initialization...")

    # Use test database
    test_db = "test_smart_downloader.db"

    # Remove test database if it exists
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)

    # Check that tables exist
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = ['media', 'downloads', 'categories', 'owner', 'preferences', 'activity_log', 'media_fts']
    for table in expected_tables:
        assert table in tables, f"Table {table} not found"

    conn.close()

    # Cleanup
    os.remove(test_db)

    print("✓ Database initialization test passed")


def test_owner_management():
    """Test owner lock functionality."""
    print("\nTesting owner management...")

    test_db = "test_owner.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)

    # Initially not locked
    assert not db.is_locked(), "Database should not be locked initially"
    print("  ✓ Initially not locked")

    # Set owner
    db.set_owner(chat_id=123456789, user_id=987654321, username="test_user")
    assert db.is_locked(), "Database should be locked after setting owner"
    print("  ✓ Locked after setting owner")

    # Get owner info
    owner = db.get_owner()
    assert owner['chat_id'] == 123456789
    assert owner['user_id'] == 987654321
    assert owner['username'] == "test_user"
    print("  ✓ Owner info correct")

    # Test authorization
    assert db.is_authorized(123456789), "Owner should be authorized"
    assert not db.is_authorized(999999999), "Non-owner should not be authorized"
    print("  ✓ Authorization works correctly")

    # Cleanup
    os.remove(test_db)

    print("✓ Owner management test passed")


def test_category_seeding():
    """Test default categories are seeded."""
    print("\nTesting category seeding...")

    test_db = "test_categories.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)

    categories = db.get_all_categories()
    assert len(categories) == 3, f"Expected 3 categories, got {len(categories)}"

    category_names = [cat['name'] for cat in categories]
    expected = ['Favorites', 'Watch Later', 'Music']
    for name in expected:
        assert name in category_names, f"Category {name} not found"

    print("  ✓ All default categories seeded")
    print(f"  Categories: {', '.join(category_names)}")

    # Cleanup
    os.remove(test_db)

    print("✓ Category seeding test passed")


def test_queue_operations():
    """Test download queue operations."""
    print("\nTesting queue operations...")

    test_db = "test_queue.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)

    # Add to queue
    id1 = db.add_to_queue(
        url="https://example.com/video1.mp4",
        source="direct",
        title="Video 1",
        file_size=1000000,
        chat_id=123456789,
        message_id=100
    )
    print(f"  ✓ Added download {id1}")

    id2 = db.add_to_queue(
        url="https://example.com/video2.mp4",
        source="direct",
        title="Video 2",
        file_size=2000000
    )
    print(f"  ✓ Added download {id2}")

    # Get next pending
    next_item = db.get_next_pending()
    assert next_item is not None, "Should have pending download"
    assert next_item['id'] == id1, "First added should be first pending (FIFO)"
    print("  ✓ FIFO ordering works")

    # Update status
    db.update_download_status(id1, "downloading")
    db.update_progress(id1, 50, download_speed=2.5, eta_seconds=200)

    # Get active download
    active = db.get_active_download()
    assert active is not None
    assert active['id'] == id1
    assert active['progress'] == 50
    assert active['download_speed'] == 2.5
    print("  ✓ Status and progress updates work")

    # Queue summary
    summary = db.get_queue_summary()
    assert summary['pending'] == 1
    assert summary['downloading'] == 1
    print(f"  ✓ Queue summary: {summary}")

    # Increment retry
    retry_count = db.increment_retry(id1)
    assert retry_count == 1
    print("  ✓ Retry count increment works")

    # Cleanup
    os.remove(test_db)

    print("✓ Queue operations test passed")


def test_media_operations():
    """Test media library operations."""
    print("\nTesting media operations...")

    test_db = "test_media.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)

    # Add media
    media_id = db.add_media(
        title="Test Movie",
        source_url="https://example.com/movie.mp4",
        source_type="direct",
        file_size=1000000000,
        hash="abc123"
    )
    print(f"  ✓ Added media {media_id}")

    # Get media
    media = db.get_media(media_id)
    assert media is not None
    assert media['title'] == "Test Movie"
    print("  ✓ Retrieved media by ID")

    # Add to category first
    db.add_media_to_category(media_id, 1)
    print("  ✓ Added media to category")

    # Get by category
    movies = db.get_media_by_category(1)
    assert len(movies) == 1
    assert movies[0]['id'] == media_id
    print("  ✓ Retrieved media by category")

    # Update file_id
    db.update_media_file_id(media_id, "BAADBAADQwADBQADIgAP")
    media = db.get_media(media_id)
    assert media['file_id'] == "BAADBAADQwADBQADIgAP"
    print("  ✓ File ID update works")

    # Toggle favorite
    is_favorite = db.toggle_favorite(media_id)
    assert is_favorite is True
    media = db.get_media(media_id)
    assert media['is_favorite'] == 1
    print("  ✓ Favorite toggle works")

    # Get favorites
    favorites = db.get_favorites()
    assert len(favorites) == 1
    assert favorites[0]['id'] == media_id
    print("  ✓ Retrieved favorites")

    # Search (FTS)
    results = db.search_media("Test")
    assert len(results) == 1
    print("  ✓ Full-text search works")

    # Duplicate check
    assert db.check_duplicate("abc123") is True
    assert db.check_duplicate("xyz789") is False
    print("  ✓ Duplicate detection works")

    # Delete media
    deleted = db.delete_media(media_id)
    assert deleted is True
    assert db.get_media(media_id) is None
    print("  ✓ Media deletion works")

    # Cleanup
    os.remove(test_db)

    print("✓ Media operations test passed")


def test_activity_logging():
    """Test activity logging."""
    print("\nTesting activity logging...")

    test_db = "test_activity.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    db = DatabaseManager(test_db)

    # Log activities
    db.log_activity(
        user_id=123456,
        chat_id=789012,
        action="download_started",
        metadata={"url": "https://example.com/test.mp4"}
    )
    print("  ✓ Logged activity")

    db.log_activity(
        user_id=123456,
        chat_id=789012,
        action="download_completed"
    )
    print("  ✓ Logged second activity")

    # Get activity log
    activities = db.get_activity_log(user_id=123456)
    assert len(activities) == 2
    assert activities[0]['action'] == "download_completed"  # Most recent first
    print("  ✓ Retrieved activity log")

    # Cleanup
    os.remove(test_db)

    print("✓ Activity logging test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Smart Downloader - Phase 1 Database Tests")
    print("=" * 60)

    try:
        test_database_initialization()
        test_owner_management()
        test_category_seeding()
        test_queue_operations()
        test_media_operations()
        test_activity_logging()

        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
