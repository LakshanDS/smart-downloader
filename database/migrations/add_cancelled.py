"""
Migration: Add cancelled column to downloads table

This migration adds a 'cancelled' column to track cancelled downloads.
Users can cancel downloads by setting this column to 1.
"""

def up(db_manager):
    """Add cancelled column to downloads table."""
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            ALTER TABLE downloads
            ADD COLUMN cancelled INTEGER DEFAULT 0
        """)
        conn.commit()
        print("Added 'cancelled' column to downloads table")

def down(db_manager):
    """Remove cancelled column from downloads table."""
    # SQLite doesn't support ALTER TABLE DROP COLUMN directly
    # This is a placeholder for reference
    print("Warning: Cannot drop column in SQLite. Manual intervention required.")
