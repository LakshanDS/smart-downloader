# Database Migration Script
# This script handles migration from old schema (fixed categories) to new schema (user-created categories with many-to-many)

import sqlite3
import os
from datetime import datetime

def migrate_database(db_path: str = 'smart_downloader.db'):
    """Migrate database to new schema."""

    print(f"🔄 Starting database migration: {db_path}")

    if not os.path.exists(db_path):
        print("❌ Database file not found")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if migration already done
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='media_categories'")
        if cursor.fetchone():
            print("✅ Migration already completed (media_categories table exists)")
            return True

        print("\n📋 Migration Steps:")
        print("1. Backup existing data...")
        print("2. Remove category column from media table...")
        print("3. Create media_categories junction table...")
        print("4. Create new categories table...")
        print("5. Seed default categories...")
        print("6. Update indexes...")

        # Step 1: Backup
        cursor.execute("SELECT * FROM media")
        old_media = cursor.fetchall()

        # Step 2: Remove category column (by recreating table)
        print("\n⏳ Step 1/6: Recreating media table without category column...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_new (
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
        """)

        # Copy data (excluding category column)
        cursor.execute("""
            INSERT INTO media_new (id, file_id, title, file_name, file_size, duration, source_url, source_type, download_date, hash, is_favorite, created_at, updated_at)
            SELECT id, file_id, title, file_name, file_size, duration, source_url, source_type, download_date, hash, is_favorite, created_at, updated_at
            FROM media
        """)

        # Drop old table and rename new one
        cursor.execute("DROP TABLE media")
        cursor.execute("ALTER TABLE media_new RENAME TO media")

        print("✅ Step 1/6 complete")

        # Step 3: Create media_categories junction table
        print("⏳ Step 2/6: Creating media_categories junction table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_categories (
                media_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (media_id, category_id),
                FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        """)

        # Step 4: Update categories table
        print("⏳ Step 3/6: Updating categories table...")

        cursor.execute("DROP TABLE IF EXISTS categories")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                emoji TEXT DEFAULT '📁',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        print("✅ Step 3/6 complete")

        # Step 5: Seed default categories
        print("⏳ Step 4/6: Seeding default categories...")

        cursor.execute("""
            INSERT INTO categories (name, emoji) VALUES
            ('Favorites', '❤️'),
            ('Watch Later', '⏰'),
            ('Music', '🎵')
            ON CONFLICT(name) DO NOTHING
        """)

        print("✅ Step 4/6 complete")

        # Step 6: Update indexes
        print("⏳ Step 5/6: Updating indexes...")

        # Drop old indexes
        cursor.execute("DROP INDEX IF EXISTS idx_media_category")
        cursor.execute("DROP INDEX IF EXISTS idx_media_favorite")
        cursor.execute("DROP INDEX IF EXISTS idx_media_date")

        # Create new indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_favorite ON media(is_favorite)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_date ON media(download_date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_categories_media ON media_categories(media_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_categories_category ON media_categories(category_id)")

        print("✅ Step 5/6 complete")

        # Step 7: Update FTS
        print("⏳ Step 6/6: Updating FTS table...")

        cursor.execute("DROP TABLE IF EXISTS media_fts")

        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
                title, file_name,
                content='media',
                content_rowid='id'
            )
        """)

        # Rebuild FTS index
        cursor.execute("""
            INSERT INTO media_fts (rowid, title, file_name)
            SELECT id, title, COALESCE(file_name, '')
            FROM media
        """)

        print("✅ Step 6/6 complete")

        conn.commit()

        print("\n✅ Migration completed successfully!")
        print(f"   - Media records preserved: {len(old_media)}")
        print(f"   - Categories table recreated")
        print(f"   - Junction table created")

        return True

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        return False

    finally:
        conn.close()


if __name__ == '__main__':
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else 'smart_downloader.db'

    print("=" * 60)
    print("Smart Downloader - Database Migration")
    print("=" * 60)

    success = migrate_database(db_path)

    print("=" * 60)

    if success:
        print("\n✅ Migration successful! Your database is ready.")
    else:
        print("\n❌ Migration failed. Please check the error above.")

    sys.exit(0 if success else 1)
