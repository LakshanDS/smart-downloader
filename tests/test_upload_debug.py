"""
Debug Upload Test - With full traceback
"""

import asyncio
import sys
import os
import traceback

root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(root_path, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, root_path)

from database.manager import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

async def test_upload():
    db = DatabaseManager('test_upload.db')

    # Get download item
    downloads = db.get_all_downloads(status='downloaded')
    if not downloads:
        print("No downloads found")
        return

    download = downloads[0]
    print(f"Testing: {download['title']}")
    print(f"Path: {download['file_path']}")

    # Import and create manager
    from upload_module import UploadManager

    manager = UploadManager(
        db=db,
        download_dir='D:\\Projects\\smart-downloader\\downloads',
        uploader=None
    )

    print("Manager created")

    # Try to process one upload
    try:
        print("Starting process_queue...")
        await manager.process_queue()
        print("process_queue completed")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

    await manager.disconnect()
    print("Done")

if __name__ == '__main__':
    asyncio.run(test_upload())
