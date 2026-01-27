# Phase 1: Database Design & Implementation

**Objective:** Build the data model and SQLite foundation that all components will depend on.

## Database Schema

### Core Tables

```sql
-- Media Library (your downloaded files)
CREATE TABLE media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    file_id TEXT,                    -- Telegram file_id from uploader bot
    file_name TEXT,
    file_size INTEGER,               -- Bytes
    duration INTEGER,                 -- Seconds (if video/audio)
    category TEXT NOT NULL,           -- 'movie', 'tv', 'porn', 'custom'
    source_url TEXT,                  -- Original URL or magnet link
    source_type TEXT,                 -- 'torrent', 'direct', 'unsupported'
    download_status TEXT DEFAULT 'pending', -- 'pending', 'downloading', 'completed', 'failed'
    uploaded_at DATETIME,             -- When sent to uploader bot
    user_id INTEGER NOT NULL,          -- Who requested this download
    chat_id INTEGER NOT NULL,         -- Chat session (per-user library)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Categories (browseable sections)
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    display_order INTEGER DEFAULT 0,
    icon TEXT,                      -- Emoji or icon identifier
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Download Queue (tracks active downloads)
CREATE TABLE downloads (
    gid TEXT PRIMARY KEY,              -- aria2c GID or unique ID
    status TEXT DEFAULT 'pending',    -- 'pending', 'active', 'completed', 'failed', 'paused'
    progress INTEGER DEFAULT 0,         -- 0-100
    download_speed INTEGER,            -- Bytes per second
    total_size INTEGER,
    downloaded INTEGER,
    eta_seconds INTEGER,               -- Estimated time remaining
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,        -- To update progress inline
    media_id INTEGER,                  -- Links to media table
    source_url TEXT,
    source_type TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Chat Sessions (for auto-clear management)
CREATE TABLE chat_sessions (
    chat_id INTEGER PRIMARY KEY,
    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
    auto_clear_enabled BOOLEAN DEFAULT 1,
    auto_clear_hours INTEGER DEFAULT 24,
    message_count INTEGER DEFAULT 0
);

-- User Preferences (per-user settings)
CREATE TABLE user_preferences (
    user_id INTEGER PRIMARY KEY,
    default_category TEXT DEFAULT 'movie',
    auto_clear_enabled BOOLEAN DEFAULT 1,
    auto_clear_hours INTEGER DEFAULT 24,
    notification_enabled BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Activity Log (for debugging/auditing)
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    action TEXT NOT NULL,             -- 'download_started', 'download_completed', 'category_browsed', etc.
    metadata TEXT,                    -- JSON string with additional data
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Indexes

```sql
-- Performance indexes
CREATE INDEX idx_media_user ON media(user_id);
CREATE INDEX idx_media_category ON media(category);
CREATE INDEX idx_media_status ON media(download_status);
CREATE INDEX idx_media_chat ON media(chat_id);
CREATE INDEX idx_downloads_chat ON downloads(chat_id);
CREATE INDEX idx_downloads_status ON downloads(status);
CREATE INDEX idx_activity_user ON activity_log(user_id, created_at);
```

## Initial Data Seeding

```sql
-- Default categories
INSERT INTO categories (name, description, display_order, icon) VALUES
('movie', 'Full-length movies and films', 1, '📽'),
('tv', 'TV shows, series, and episodes', 2, '📺'),
('porn', 'Adult content', 3, '🔞'),
('custom', 'Uncategorized or custom downloads', 4, '📁');
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
            
            # Create tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS media (...)
            """)  # (full schema from above)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (...)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (...)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (...)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (...)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (...)
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_user ON media(user_id)")
            # ... (other indexes)
            
            conn.commit()
            
            # Seed default categories if empty
            cursor.execute("SELECT COUNT(*) FROM categories")
            if cursor.fetchone()[0] == 0:
                self._seed_categories(cursor)
                conn.commit()
    
    def _seed_categories(self, cursor):
        """Insert default categories."""
        categories = [
            ('movie', 'Full-length movies and films', 1, '📽'),
            ('tv', 'TV shows, series, and episodes', 2, '📺'),
            ('porn', 'Adult content', 3, '🔞'),
            ('custom', 'Uncategorized or custom downloads', 4, '📁'),
        ]
        
        cursor.executemany("""
            INSERT INTO categories (name, description, display_order, icon) VALUES (?, ?, ?, ?)
        """, categories)
    
    # === Media Operations ===
    
    def add_media(self, title: str, category: str, source_url: str, 
                  source_type: str, user_id: int, chat_id: int,
                  file_id: Optional[str] = None) -> int:
        """Add new media entry."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO media (title, category, source_url, source_type, 
                                user_id, chat_id, file_id, download_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (title, category, source_url, source_type, user_id, chat_id, file_id))
            
            media_id = cursor.lastrowid
            conn.commit()
            return media_id
    
    def update_media_file_id(self, media_id: int, file_id: str):
        """Update with Telegram file_id after upload."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE media 
                SET file_id = ?, 
                    download_status = 'completed',
                    uploaded_at = datetime.now().isoformat(),
                    updated_at = datetime.now().isoformat()
                WHERE id = ?
            """, (file_id, media_id))
            conn.commit()
    
    def update_media_status(self, media_id: int, status: str):
        """Update download status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE media 
                SET download_status = ?, updated_at = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), media_id))
            conn.commit()
    
    def get_media_by_category(self, category: str, user_id: int, 
                            chat_id: int) -> List[Dict]:
        """Get all media in a category for user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, file_id, file_size, duration, 
                       category, source_url, source_type, 
                       download_status, uploaded_at, created_at
                FROM media 
                WHERE category = ? AND user_id = ? AND chat_id = ?
                ORDER BY created_at DESC
            """, (category, user_id, chat_id))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_library(self, user_id: int, chat_id: int) -> Dict[str, List[Dict]]:
        """Get all media organized by category."""
        categories = self.get_all_categories()
        library = {}
        
        for cat in categories:
            library[cat['name']] = self.get_media_by_category(
                cat['name'], user_id, chat_id)
        
        return library
    
    # === Download Operations ===
    
    def add_download(self, gid: str, source_url: str, source_type: str,
                  chat_id: int, message_id: int, 
                  media_id: Optional[int] = None) -> None:
        """Add new download to queue."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO downloads (gid, source_url, source_type, 
                                  chat_id, message_id, media_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (gid, source_url, source_type, chat_id, message_id, media_id))
            conn.commit()
    
    def update_download_progress(self, gid: str, progress: int, 
                              downloaded: int, speed: int, eta: int):
        """Update download progress."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads 
                SET progress = ?, downloaded = ?, 
                    download_speed = ?, eta_seconds = ?,
                    updated_at = ?
                WHERE gid = ?
            """, (progress, downloaded, speed, eta, datetime.now().isoformat(), gid))
            conn.commit()
    
    def complete_download(self, gid: str, total_size: int, media_id: int):
        """Mark download as complete and link to media."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE downloads 
                SET status = 'completed', total_size = ?, 
                    media_id = ?, updated_at = ?
                WHERE gid = ?
            """, (total_size, media_id, datetime.now().isoformat(), gid))
            
            # Update media status too
            cursor.execute("""
                UPDATE media 
                SET download_status = 'completed', updated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), media_id))
            
            conn.commit()
    
    def get_active_downloads(self, chat_id: int) -> List[Dict]:
        """Get all active downloads for a chat."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gid, status, progress, download_speed, 
                       total_size, downloaded, eta_seconds, source_url
                FROM downloads 
                WHERE chat_id = ? AND status IN ('active', 'pending')
                ORDER BY started_at DESC
            """, (chat_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # === Category Operations ===
    
    def get_all_categories(self) -> List[Dict]:
        """Get all categories."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, description, display_order, icon
                FROM categories
                ORDER BY display_order ASC
            """)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_category(self, name: str) -> Optional[Dict]:
        """Get category by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM categories WHERE name = ?
            """, (name,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # === Chat Session Operations ===
    
    def update_chat_activity(self, chat_id: int):
        """Update last activity timestamp."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO chat_sessions (chat_id, last_activity, message_count)
                VALUES (?, ?, 1)
                ON CONFLICT(chat_id) DO UPDATE SET 
                    last_activity = ?, message_count = message_count + 1
            """, (chat_id, datetime.now().isoformat(), datetime.now().isoformat()))
            
            conn.commit()
    
    def get_chats_to_clear(self, hours: int) -> List[int]:
        """Get chats that need auto-clear."""
        threshold = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_id FROM chat_sessions
                WHERE auto_clear_enabled = 1 
                  AND auto_clear_hours = ?
                  AND datetime(last_activity, '+{hours} hours') < datetime('now')
            """, (hours,))
            
            return [row['chat_id'] for row in cursor.fetchall()]
    
    # === Logging ===
    
    def log_activity(self, user_id: int, chat_id: int, 
                   action: str, metadata: Optional[Dict] = None):
        """Log user activity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO activity_log (user_id, chat_id, action, metadata)
                VALUES (?, ?, ?, ?)
            """, (user_id, chat_id, action, json.dumps(metadata) if metadata else None))
            conn.commit()
```

## Implementation Tasks

- [ ] Create `database.py` with DatabaseManager class
- [ ] Implement all table schemas
- [ ] Add indexes for performance
- [ ] Seed default categories
- [ ] Write unit tests for CRUD operations
- [ ] Test concurrent access safety
- [ ] Add migration support (future version upgrades)

## Dependencies

```python
# requirements.txt
sqlite3  # Built-in, but document version requirements
```

## Notes

- **Single-file database:** Keeps it simple for now
- **Connection pooling:** Using context managers for thread safety
- **Timestamps:** ISO format strings (easier to work with)
- **Future scaling:** Can migrate to PostgreSQL if needed
