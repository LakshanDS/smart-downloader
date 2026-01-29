# Migration: Add priority column to downloads table
import sqlite3
import os
import sys

def migrate(db_path: str = 'dev.db'):
    """Add priority column to downloads table."""

    print(f"[*] Adding priority column: {db_path}")

    if not os.path.exists(db_path):
        print("[!] Database file not found")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(downloads)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'priority' in columns:
            print("[+] Column 'priority' already exists")
            return True

        # Add priority column
        print("[*] Adding priority column...")
        cursor.execute("ALTER TABLE downloads ADD COLUMN priority INTEGER DEFAULT 0")

        conn.commit()
        print("[+] Migration completed!")
        return True

    except Exception as e:
        conn.rollback()
        print(f"[!] Migration failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
