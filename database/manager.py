"""
Database Module - Smart Downloader

Phase 1: Database Design & Foundation
Implements SQLite database with owner lock, queue management, and media library.

Updated: User-created categories with many-to-many relationship (Phase 8)
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import contextmanager
import json
import logging

logger = logging.getLogger(__name__)


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
                self._sql_media_categories(),
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

            # Migration: Add priority column if missing
            cursor.execute("PRAGMA table_info(downloads)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'priority' not in columns:
                cursor.execute("ALTER TABLE downloads ADD COLUMN priority INTEGER DEFAULT 0")
                logger.info("Added priority column to downloads table")

            # Migration: Add pause/resume columns if missing
            if 'can_pause' not in columns:
                cursor.execute("ALTER TABLE downloads ADD COLUMN can_pause BOOLEAN DEFAULT 1")
                logger.info("Added can_pause column to downloads table")
            if 'paused' not in columns:
                cursor.execute("ALTER TABLE downloads ADD COLUMN paused BOOLEAN DEFAULT 0")
                logger.info("Added paused column to downloads table")
            if 'pause_reason' not in columns:
                cursor.execute("ALTER TABLE downloads ADD COLUMN pause_reason TEXT")
                logger.info("Added pause_reason column to downloads table")

            # Migration: Add file_id and file_path columns for uploads
            if 'file_id' not in columns:
                cursor.execute("ALTER TABLE downloads ADD COLUMN file_id TEXT")
                logger.info("Added file_id column to downloads table")
            if 'file_path' not in columns:
                cursor.execute("ALTER TABLE downloads ADD COLUMN file_path TEXT")
                logger.info("Added file_path column to downloads table")

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
            result = cursor.fetchone()[0]
            conn.commit()
            return result

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

    def get_download(self, download_id: int) -> Optional[Dict]:
        """Get download by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM downloads WHERE id = ?", (download_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_downloads(self, status: str = None) -> List[Dict]:
        """Get all downloads, optionally filtered by status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT * FROM downloads
                    WHERE status = ?
                    ORDER BY added_date DESC
                """, (status,))
            else:
                cursor.execute("""
                    SELECT * FROM downloads
                    ORDER BY added_date DESC
                """)

            return [dict(row) for row in cursor.fetchall()]

    def update_download_metadata(self, download_id: int, title: str = None,
                             file_size: int = None):
        """Update download metadata."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET title = COALESCE(?, title),
                    file_size = COALESCE(?, file_size)
                WHERE id = ?
            """, (title, file_size, download_id))
            conn.commit()

    def update_file_path(self, download_id: int, file_path: str):
        """Update file path after download."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET file_path = ?
                WHERE id = ?
            """, (file_path, download_id))
            conn.commit()

    def get_downloads_by_status(self, status: str) -> List[Dict]:
        """Get all downloads with specific status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads
                WHERE status = ?
                ORDER BY added_date ASC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]

    def mark_cancelled(self, download_id: int):
        """Mark download as cancelled."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET cancelled = 1, status = 'cancelled'
                WHERE id = ?
            """, (download_id,))
            conn.commit()

    def mark_completed(self, download_id: int):
        """Mark download as completed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET status = 'completed', progress = 100, updated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), download_id))
            conn.commit()

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

    def get_all_media(self) -> List[Dict]:
        """Get all media."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM media
                ORDER BY created_at DESC
            """)

            return [dict(row) for row in cursor.fetchall()]

    def get_media(self, media_id: int) -> Optional[Dict]:
        """Get media by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM media WHERE id = ?", (media_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def check_duplicate(self, hash: str) -> bool:
        """Check if file with this hash already exists."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM media WHERE hash = ? LIMIT 1", (hash,))
            return cursor.fetchone() is not None

    def delete_media(self, media_id: int) -> bool:
        """Delete media from library."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM media WHERE id = ?", (media_id,))
            deleted = cursor.rowcount > 0
            # Also delete from FTS
            cursor.execute("DELETE FROM media_fts WHERE rowid = ?", (media_id,))
            conn.commit()
            return deleted

    # === Category Operations (User-Created with Many-to-Many) ===

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

    def get_category(self, name: str) -> Optional[Dict]:
        """Get category by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

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

    def get_activity_log(self, user_id: int = None,
                        limit: int = 100) -> List[Dict]:
        """Get activity log, optionally filtered by user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT * FROM activity_log
                    WHERE user_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM activity_log
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

    # === Preferences ===

    def get_preferences(self, chat_id: int) -> Optional[Dict]:
        """Get user preferences."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM preferences WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_preferences(self, chat_id: int, **kwargs) -> bool:
        """Update user preferences."""
        allowed_fields = {'default_category', 'auto_clear_enabled', 'auto_clear_hours'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not updates:
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [datetime.now().isoformat(), chat_id]

            cursor.execute(f"""
                UPDATE preferences
                SET {set_clause}, updated_at = ?
                WHERE chat_id = ?
            """, values)

            conn.commit()
            return cursor.rowcount > 0

    # === SQL Statements (Private) ===

    def _sql_media(self):
        """Media library table schema."""
        return """
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                title TEXT NOT NULL,
                file_name TEXT,
                file_size INTEGER,
                duration INTEGER,
                source_url TEXT,
                source_type TEXT,
                download_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                hash TEXT,
                is_favorite BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """

    def _sql_downloads(self):
        """Download queue table schema."""
        return """
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
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """

    def _sql_categories(self):
        """Categories table schema (user-created)."""
        return """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                emoji TEXT DEFAULT '📁',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """

    def _sql_media_categories(self):
        """Media-Categories junction table (many-to-many)."""
        return """
            CREATE TABLE IF NOT EXISTS media_categories (
                media_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (media_id, category_id),
                FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """

    def _sql_owner(self):
        """Owner lock table schema."""
        return """
            CREATE TABLE IF NOT EXISTS owner (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                chat_id INTEGER UNIQUE NOT NULL,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                locked_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """

    def _sql_preferences(self):
        """Preferences table schema."""
        return """
            CREATE TABLE IF NOT EXISTS preferences (
                chat_id INTEGER PRIMARY KEY,
                auto_clear_enabled BOOLEAN DEFAULT 0,
                auto_clear_hours INTEGER DEFAULT 24,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES owner(chat_id)
            )
        """

    def _sql_activity_log(self):
        """Activity log table schema."""
        return """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """

    def _sql_indexes(self):
        """Database indexes for performance."""
        return [
            "CREATE INDEX IF NOT EXISTS idx_media_favorite ON media(is_favorite)",
            "CREATE INDEX IF NOT EXISTS idx_media_date ON media(download_date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status)",
            "CREATE INDEX IF NOT EXISTS idx_downloads_chat ON downloads(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_media_categories_media ON media_categories(media_id)",
            "CREATE INDEX IF NOT EXISTS idx_media_categories_category ON media_categories(category_id)"
        ]

    def _sql_fts(self):
        """Full-text search table schema."""
        return """
            CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
                title, file_name,
                content='media',
                content_rowid='id'
            )
        """

    def _seed_categories(self, cursor):
        """Seed default categories."""
        cursor.execute("""
            INSERT INTO categories (name, emoji) VALUES
            ('Favorites', '❤️'),
            ('Watch Later', '⏰'),
            ('Music', '🎵')
        """)

    def close(self):
        """Close database connections if needed."""
        pass  # Connections are managed via context manager

    # Queue CRUD operations

    def get_queue_items(self, status: str = 'pending') -> List[Dict]:
        """Get all queue items, ordered by priority and added_date."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM downloads
                WHERE status = ?
                ORDER BY priority DESC, added_date ASC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]

    def delete_queue_item(self, item_id: int) -> bool:
        """Delete a queue item by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM downloads WHERE id = ?", (item_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_queue_url(self, item_id: int, new_url: str) -> bool:
        """Update the URL of a queue item."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE downloads
                SET url = ?, updated_at = ?
                WHERE id = ?
            """, (new_url, datetime.now().isoformat(), item_id))
            conn.commit()
            return cursor.rowcount > 0

    def reorder_queue(self, item_id: int, new_position: int) -> bool:
        """Reorder queue item by setting priority (higher priority = processes sooner)."""
        with self.get_connection() as conn:
            # Use negative position as priority (so position 1 gets highest priority)
            cursor = conn.execute("""
                UPDATE downloads
                SET priority = ?, updated_at = ?
                WHERE id = ?
            """, (-new_position, datetime.now().isoformat(), item_id))
            conn.commit()
            return cursor.rowcount > 0

    def set_queue_priority(self, item_id: int, priority: int) -> bool:
        """Set priority for a queue item (higher = processes sooner)."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE downloads
                SET priority = ?, updated_at = ?
                WHERE id = ?
            """, (priority, datetime.now().isoformat(), item_id))
            conn.commit()
            return cursor.rowcount > 0

    # === Pause/Resume/Cancel Operations ===

    def set_paused(self, download_id: int, paused: bool = True, reason: str = None) -> bool:
        """Set paused state for a download."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE downloads
                SET paused = ?, pause_reason = ?, updated_at = ?
                WHERE id = ?
            """, (1 if paused else 0, reason, datetime.now().isoformat(), download_id))
            conn.commit()
            return cursor.rowcount > 0

    def is_paused(self, download_id: int) -> bool:
        """Check if download is paused."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT paused FROM downloads WHERE id = ?", (download_id,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False

    def cancel_download(self, download_id: int) -> bool:
        """Cancel a download (mark as failed with user_cancelled status)."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE downloads
                SET status = 'failed', error_message = 'Cancelled by user', updated_at = ?
                WHERE id = ? AND status NOT IN ('completed', 'failed')
            """, (datetime.now().isoformat(), download_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_active_downloads(self) -> List[Dict]:
        """Get all active downloads (pending, downloading, paused)."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM downloads
                WHERE status IN ('pending', 'downloading')
                ORDER BY
                    CASE WHEN paused = 1 THEN 1 ELSE 0 END,
                    priority DESC,
                    added_date ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_most_recent_download(self) -> Dict:
        """Get the most recently added/updated download (for post-completion display)."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM downloads
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_queue_snapshot_count(self) -> int:
        """Get total count including active and pending (for queue counter display)."""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM downloads
                WHERE status IN ('pending', 'downloading')
            """)
            return cursor.fetchone()[0]

    def get_queue_position(self, download_id: int) -> tuple[int, int]:
        """Get (position, total) for queue display."""
        with self.get_connection() as conn:
            # Get total active items
            cursor = conn.execute("""
                SELECT COUNT(*) FROM downloads
                WHERE status IN ('pending', 'downloading')
            """)
            total = cursor.fetchone()[0]

            # Get position (1-indexed)
            cursor.execute("""
                SELECT COUNT(*) + 1 FROM downloads d
                WHERE d.status IN ('pending', 'downloading')
                  AND d.added_date < (SELECT added_date FROM downloads WHERE id = ?)
            """, (download_id,))
            position = cursor.fetchone()[0]

            return (position, total) if total > 0 else (0, 0)

    # === Pooler Queries ===

    def get_next_pending_download(self) -> Optional[Dict]:
        """Get next pending download, respecting priority and pause state.

        Also picks up items stuck in 'downloading' status (e.g., after bot restart).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads
                WHERE status IN ('pending', 'downloading')
                  AND paused = 0
                ORDER BY
                    CASE WHEN status = 'downloading' THEN 0 ELSE 1 END,
                    priority DESC,
                    added_date ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_next_completed_upload(self) -> Optional[Dict]:
        """Get next completed download ready for upload."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM downloads
                WHERE status = 'downloaded'
                  AND file_id IS NULL
                ORDER BY added_date ASC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_download_file_id(self, download_id: int, file_id: str,
                                file_path: str = None):
        """Update download with Telegram file_id after upload."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads
                SET file_id = ?, file_path = ?, status = 'uploaded', updated_at = ?
                WHERE id = ?
            """, (file_id, file_path, datetime.now().isoformat(), download_id))
            conn.commit()
