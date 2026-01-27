# Phase 1: Database Design & Foundation

**Objective:** Build the data model and SQLite foundation for a single-user personal bot with queue-based download system.

## Key Changes from Original Plan

- **Single-user focus**: Owner chat ID lock, no multi-user isolation
- **Queue-based downloads**: Sequential processing, one-at-a-time
- **Metadata-first validation**: File size stored before download
- **Retry tracking**: Exponential backoff (0s → 2min → 8min)
- **Favorites system**: Watch Later functionality
- **Progress tracking**: Real-time speed, ETA, upload progress
- **Flexible categories**: User-created folders with many-to-many relationship

## Database Schema

### Core Tables

```sql
-- Media Library (completed downloads only)
CREATE TABLE media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT UNIQUE,                    -- Telegram file_id from userbot
    title TEXT NOT NULL,
    file_name TEXT,
    file_size INTEGER,                      -- Bytes
    duration INTEGER,                       -- Seconds (if video/audio)
    source_url TEXT,                        -- Original URL or magnet link
    source_type TEXT,                       -- 'torrent', 'direct', 'crawler'
    download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    hash TEXT,                              -- For duplicate detection
    is_favorite BOOLEAN DEFAULT 0,          -- Watch Later / Favorites
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Download Queue (pending + active downloads)
CREATE TABLE downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    source TEXT,                            -- 'torrent', 'direct', 'crawler'
    status TEXT DEFAULT 'pending',          -- 'pending', 'downloading', 'uploading', 'completed', 'failed'
    progress INTEGER DEFAULT 0,             -- 0-100
    retry_count INTEGER DEFAULT 0,          -- Track retry attempts
    added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    file_size INTEGER,                      -- Pre-validated size (bytes)
    title TEXT,                             -- Extracted from metadata
    download_speed REAL,                    -- Current speed (MB/s)
    upload_speed REAL,                      -- Current upload speed (MB/s)
    eta_seconds INTEGER,                    -- Estimated time remaining
    message_id INTEGER,                     -- Bot progress message ID
    chat_id INTEGER,                        -- For progress updates
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Categories (user-created folders)
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,              -- User-defined name
    emoji TEXT DEFAULT '📁',               -- Folder icon
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Media-Categories junction (many-to-many)
CREATE TABLE media_categories (
    media_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (media_id, category_id),
    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

-- Owner lock (single-user only)
CREATE TABLE owner (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Singleton table
    chat_id INTEGER UNIQUE NOT NULL,        -- Owner's Telegram chat ID
    user_id INTEGER UNIQUE NOT NULL,        -- Owner's Telegram user ID
    username TEXT,                          -- Owner's username
    locked_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- User preferences (single row for owner)
CREATE TABLE preferences (
    chat_id INTEGER PRIMARY KEY,            -- Owner's chat ID (foreign key)
    auto_clear_enabled BOOLEAN DEFAULT 0,   -- Optional feature
    auto_clear_hours INTEGER DEFAULT 24,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES owner(chat_id)
);

-- Activity Log (for debugging/auditing)
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    action TEXT NOT NULL,                   -- 'download_started', 'download_completed', etc.
    metadata TEXT,                          -- JSON string with additional data
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Indexes

```sql
-- Performance indexes
CREATE INDEX idx_media_favorite ON media(is_favorite);
CREATE INDEX idx_media_date ON media(download_date DESC);
CREATE INDEX idx_downloads_status ON downloads(status);
CREATE INDEX idx_downloads_chat ON downloads(chat_id);
CREATE INDEX idx_activity_user ON activity_log(user_id, created_at DESC);

-- Junction table indexes (for many-to-many queries)
CREATE INDEX idx_media_categories_media ON media_categories(media_id);
CREATE INDEX idx_media_categories_category ON media_categories(category_id);

-- Full-text search for media titles
CREATE VIRTUAL TABLE media_fts USING fts5(
    title, file_name,
    content='media',
    content_rowid='id'
);
```

## Initial Data Seeding

```sql
-- Optional seed with helpful defaults (can be deleted by user)
INSERT INTO categories (name, emoji) VALUES
('Favorites', '❤️'),
('Watch Later', '⏰'),
('Music', '🎵')
ON CONFLICT(name) DO NOTHING;  -- Only if not exists
```

## Database Module (`database.py`)

### API Design

```python
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager
import json

class DatabaseManager:
    """Main database interface for smart downloader."""

    def __init__(self, db_path: str = 'smart_downloader.db'):
        self.db_path = db_path
        self._initialize()

    @contextmanager
    def get_connection(self):
        """Context manager for safe connection handling."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self):
        """Create tables and indexes if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create all tables
            for table_sql in [
                self._sql_media(),
                self._sql_downloads(),
                self._sql_categories(),
                self._sql_owner(),
                self._sql_preferences(),
                self._sql_activity_log()
            ]:
                cursor.execute(table_sql)

            # Create indexes
            for index_sql in self._sql_indexes():
                cursor.execute(index_sql)

            # Create FTS table
            cursor.execute(self._sql_fts())

            conn.commit()

            # Seed categories if empty
            cursor.execute("SELECT COUNT(*) FROM categories")
            if cursor.fetchone()[0] == 0:
                self._seed_categories(cursor)
                conn.commit()

    # === Owner Management (Single-User) ===

    def is_locked(self) -> bool:
        """Check if bot is already locked to an owner."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM owner")
            return cursor.fetchone() is not None

    def set_owner(self, chat_id: int, user_id: int, username: str = None) -> bool:
        """Lock bot to an owner (one-time setup)."""
        if self.is_locked():
            raise ValueError("Bot is already locked to an owner")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO owner (id, chat_id, user_id, username)
                VALUES (1, ?, ?, ?)
            """, (chat_id, user_id, username))

            # Also create default preferences
            cursor.execute("""
                INSERT INTO preferences (chat_id)
                VALUES (?)
            """, (chat_id,))

            conn.commit()
            return True

    def get_owner(self) -> Optional[Dict]:
        """Get owner information."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM owner")
            row = cursor.fetchone()
            return dict(row) if row else None

    def is_authorized(self, chat_id: int) -> bool:
        """Check if chat_id is the owner."""
        owner = self.get_owner()
        return owner and owner['chat_id'] == chat_id

    # === Queue Operations ===

    def add_to_queue(self, url: str, source: str, title: str = None,
                     file_size: int = None, chat_id: int = None,
                     message_id: int = None) -> int:
        """Add download to queue."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO downloads (url, source, title, file_size, chat_id, message_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (url, source, title, file_size, chat_id, message_id))

            queue_id = cursor.lastrowid
            conn.commit()
            return queue_id

    def get_next_pending(self) -> Optional[Dict]:
        """Get next pending download (FIFO)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads
                WHERE status = 'pending'
                ORDER BY added_date ASC
                LIMIT 1
            """)

            row = cursor.fetchone()
            return dict(row) if row else None

    def update_download_status(self, download_id: int, status: str,
                               error_message: str = None):
        """Update download status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET status = ?, error_message = ?, updated_at = ?
                WHERE id = ?
            """, (status, error_message, datetime.now().isoformat(), download_id))
            conn.commit()

    def update_progress(self, download_id: int, progress: int,
                       download_speed: float = None, upload_speed: float = None,
                       eta_seconds: int = None):
        """Update download/upload progress."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET progress = ?,
                    download_speed = COALESCE(?, download_speed),
                    upload_speed = COALESCE(?, upload_speed),
                    eta_seconds = COALESCE(?, eta_seconds),
                    updated_at = ?
                WHERE id = ?
            """, (progress, download_speed, upload_speed, eta_seconds,
                  datetime.now().isoformat(), download_id))
            conn.commit()

    def increment_retry(self, download_id: int) -> int:
        """Increment retry count, return new count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET retry_count = retry_count + 1, updated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), download_id))

            cursor.execute("SELECT retry_count FROM downloads WHERE id = ?", (download_id,))
            return cursor.fetchone()[0]

    def get_queue_summary(self) -> Dict:
        """Get queue statistics for display."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'downloading') as downloading,
                    COUNT(*) FILTER (WHERE status = 'uploading') as uploading,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed
                FROM downloads
            """)

            return dict(cursor.fetchone())

    def get_active_download(self) -> Optional[Dict]:
        """Get currently active download (for progress display)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads
                WHERE status IN ('downloading', 'uploading')
                LIMIT 1
            """)

            row = cursor.fetchone()
            return dict(row) if row else None

    # === Media Operations ===

    def add_media(self, title: str, source_url: str, source_type: str,
                  file_size: int, file_id: str = None, hash: str = None,
                  category_ids: List[int] = None) -> int:
        """Add completed media to library."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO media (title, source_url, source_type, file_size, file_id, hash)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, source_url, source_type, file_size, file_id, hash))

            media_id = cursor.lastrowid

            # Update FTS index
            cursor.execute("""
                INSERT INTO media_fts (rowid, title, file_name)
                VALUES (?, ?, '')
            """, (media_id, title))

            # Add to categories if provided
            if category_ids:
                for cat_id in category_ids:
                    cursor.execute("""
                        INSERT INTO media_categories (media_id, category_id)
                        VALUES (?, ?)
                    """, (media_id, cat_id))

            conn.commit()
            return media_id

    def update_media_file_id(self, media_id: int, file_id: str):
        """Update with Telegram file_id after upload."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE media
                SET file_id = ?, updated_at = ?
                WHERE id = ?
            """, (file_id, datetime.now().isoformat(), media_id))
            conn.commit()

    def toggle_favorite(self, media_id: int) -> bool:
        """Toggle favorite status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE media
                SET is_favorite = NOT is_favorite, updated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), media_id))

            cursor.execute("SELECT is_favorite FROM media WHERE id = ?", (media_id,))
            result = cursor.fetchone()
            conn.commit()
            return bool(result[0]) if result else False

    def get_favorites(self) -> List[Dict]:
        """Get all favorited media."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM media
                WHERE is_favorite = 1
                ORDER BY created_at DESC
            """)

            return [dict(row) for row in cursor.fetchall()]

    def search_media(self, query: str) -> List[Dict]:
        """Full-text search in media titles."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.* FROM media m
                INNER JOIN media_fts fts ON m.id = fts.rowid
                WHERE media_fts MATCH ?
                ORDER BY m.created_at DESC
            """, (query,))

            return [dict(row) for row in cursor.fetchall()]

    def get_media_by_category(self, category_id: int) -> List[Dict]:
        """Get all media in a category (many-to-many)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.* FROM media m
                INNER JOIN media_categories mc ON m.id = mc.media_id
                WHERE mc.category_id = ?
                ORDER BY m.created_at DESC
            """, (category_id,))

            return [dict(row) for row in cursor.fetchall()]

    def check_duplicate(self, hash: str) -> bool:
        """Check if file with this hash already exists."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM media WHERE hash = ? LIMIT 1", (hash,))
            return cursor.fetchone() is not None

    # === Category Operations ===

    def create_category(self, name: str, emoji: str = '📁') -> int:
        """Create a new category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO categories (name, emoji)
                VALUES (?, ?)
            """, (name, emoji))
            conn.commit()
            return cursor.lastrowid

    def delete_category(self, category_id: int):
        """Delete a category (cascades to media_categories)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            conn.commit()

    def rename_category(self, category_id: int, new_name: str):
        """Rename a category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE categories SET name = ? WHERE id = ?
            """, (new_name, category_id))
            conn.commit()

    def get_all_categories(self) -> List[Dict]:
        """Get all categories."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM categories
                ORDER BY created_at ASC
            """)

            return [dict(row) for row in cursor.fetchall()]

    def add_media_to_category(self, media_id: int, category_id: int):
        """Add media to a category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO media_categories (media_id, category_id)
                VALUES (?, ?)
            """, (media_id, category_id))
            conn.commit()

    def remove_media_from_category(self, media_id: int, category_id: int):
        """Remove media from a category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM media_categories
                WHERE media_id = ? AND category_id = ?
            """, (media_id, category_id))
            conn.commit()

    def get_media_categories(self, media_id: int) -> List[Dict]:
        """Get all categories for a media item."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.* FROM categories c
                INNER JOIN media_categories mc ON c.id = mc.category_id
                WHERE mc.media_id = ?
                ORDER BY c.name ASC
            """, (media_id,))

            return [dict(row) for row in cursor.fetchall()]

    # === Logging ===

    def log_activity(self, user_id: int, chat_id: int,
                    action: str, metadata: Optional[Dict] = None):
        """Log activity for debugging."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO activity_log (user_id, chat_id, action, metadata)
                VALUES (?, ?, ?, ?)
            """, (user_id, chat_id, action, json.dumps(metadata) if metadata else None))
            conn.commit()

    # === SQL Statements (Private) ===

    def _sql_media(self):
        return """CREATE TABLE IF NOT EXISTS media (...)"""

    # ... (other SQL methods)
```

## Implementation Tasks

- [ ] Create `database.py` with DatabaseManager class
- [ ] Implement all table schemas (single-user, queue, favorites)
- [ ] Add indexes for performance
- [ ] Add full-text search for media titles
- [ ] Seed default categories
- [ ] Write unit tests for CRUD operations
- [ ] Test owner lock functionality
- [ ] Test queue FIFO ordering
- [ ] Add migration support (future version upgrades)

## Dependencies

```python
# requirements.txt
# sqlite3 is built-in, no additional dependencies needed
```

## Notes

- **Single-file database:** Keeps it simple for personal use
- **Owner lock:** One-time setup, cannot be changed
- **Queue system:** FIFO ordering, one-at-a-time processing
- **Favorites:** Simple boolean flag for Watch Later
- **Full-text search:** Fast title search via FTS5
- **Duplicate detection:** Hash-based comparison
