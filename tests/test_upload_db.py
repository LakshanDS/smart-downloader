"""
Test Database Setup for Upload Module

Creates isolated test database with same structure as production.
"""

import sqlite3
import os
from datetime import datetime

TEST_DB_PATH = 'test_upload.db'


def create_test_database():
    """Create test database with downloads table."""
    # Remove existing test database
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        print(f"Removed existing test database: {TEST_DB_PATH}")

    # Create new database
    conn = sqlite3.connect(TEST_DB_PATH)
    cursor = conn.cursor()

    # Create downloads table (same structure as production)
    cursor.execute("""
        CREATE TABLE downloads (
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
            file_id TEXT,
            file_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    print(f"Created test database: {TEST_DB_PATH}")
    return conn


def add_test_download(conn, url: str, title: str, status: str = 'downloaded',
                      file_size: int = None, file_path: str = None):
    """Add a test download record."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO downloads (url, source, status, title, file_size, file_path, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url, 'test', status, title, file_size, file_path, datetime.now().isoformat()))
    conn.commit()
    download_id = cursor.lastrowid
    print(f"Added test download: id={download_id}, title={title}, status={status}")
    return download_id


def populate_test_data(conn):
    """Add test download records for existing files."""
    download_dir = 'D:\\Projects\\smart-downloader\\downloads'

    test_files = [
        {
            'url': 'https://example.com/test1.exe',
            'title': 'Hikaduwe akka hotel.pdf',
            'file_path': os.path.join(download_dir, 'Hikaduwe akka hotel.pdf')
        },
        {
            'url': 'https://example.com/test2.png',
            'title': 'Untitled design(3).png',
            'file_path': os.path.join(download_dir, 'Untitled design(3).png')
        },
        {
            'url': 'https://example.com/test3.exe',
            'title': 'ChromeSetup.exe',
            'file_path': os.path.join(download_dir, 'ChromeSetup.exe')
        },
        {
            'url': 'https://example.com/test4.mp4',
            'title': 'job_051b98d3af00.mp4',
            'file_path': os.path.join(download_dir, 'job_051b98d3af00.mp4')
        }
    ]

    for file_info in test_files:
        file_path = file_info['file_path']
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            add_test_download(
                conn,
                url=file_info['url'],
                title=file_info['title'],
                status='downloaded',
                file_size=file_size,
                file_path=file_path
            )
        else:
            print(f"Warning: File not found: {file_path}")

    # Add a failed download test (no file)
    add_test_download(
        conn,
        url='https://example.com/failed.mp4',
        title='Nonexistent File.mp4',
        status='downloaded',
        file_size=999999,
        file_path=os.path.join(download_dir, 'nonexistent.mp4')
    )


def print_test_status(conn):
    """Print current test database status."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, status, file_size, file_id, file_path FROM downloads")
    rows = cursor.fetchall()

    print("\n" + "="*80)
    print("TEST DATABASE STATUS")
    print("="*80)
    print(f"{'ID':<5} {'Title':<30} {'Status':<12} {'Size (MB)':<12} {'File ID':<20}")
    print("-"*80)

    for row in rows:
        id, title, status, file_size, file_id, file_path = row
        size_mb = f"{file_size / (1024*1024):.2f}" if file_size else "N/A"
        file_id_display = file_id[:20] if file_id else "NULL"
        print(f"{id:<5} {title[:28]:<30} {status:<12} {size_mb:<12} {file_id_display:<20}")

    print("="*80 + "\n")


if __name__ == '__main__':
    print("Setting up test database for upload module...")

    conn = create_test_database()
    populate_test_data(conn)
    print_test_status(conn)

    print(f"\nTest database ready: {TEST_DB_PATH}")
    print("You can now run the upload test script.")
