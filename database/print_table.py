"""Print downloads table content to markdown file."""

import sqlite3
from datetime import datetime
from pathlib import Path

# Database path
DB_PATH = "dev.db"

# Output path
OUTPUT_DIR = Path(__file__).parent.parent / "database"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "downloads_table.md"

def format_size(size_bytes):
    """Format size to human readable."""
    if not size_bytes:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def print_downloads_table():
    """Query and print downloads table to markdown file."""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all downloads
    cursor.execute("""
        SELECT * FROM downloads
        ORDER BY id DESC
    """)
    rows = cursor.fetchall()

    conn.close()

    # Build markdown content
    lines = [
        "# Downloads Table",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total items: {len(rows)}",
        "",
        "| ID | URL | Source | Status | Progress | Paused | Priority | File Path | Added |",
        "|---|-----|--------|--------|----------|--------|----------|-----------|-------|"
    ]

    for row in rows:
        row_dict = dict(row)
        file_path = (row_dict.get('file_path') or '')[:40] if row_dict.get('file_path') else 'None'
        lines.append(
            f"| {row_dict.get('id')} "
            f"| `{(row_dict.get('url') or '')[:40]}...` "
            f"| {row_dict.get('source')} "
            f"| {row_dict.get('status')} "
            f"| {row_dict.get('progress')}% "
            f"| {row_dict.get('paused')} "
            f"| {row_dict.get('priority')} "
            f"| `{file_path}`... "
            f"| {row_dict.get('added_date')} |"
        )

    content = "\n".join(lines)

    # Write to file
    OUTPUT_FILE.write_text(content)
    print(f"OK Table written to: {OUTPUT_FILE}")
    print(f"   Total items: {len(rows)}")

if __name__ == "__main__":
    print_downloads_table()
