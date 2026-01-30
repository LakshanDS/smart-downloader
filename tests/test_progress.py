"""
Test Progress Callback Directly
"""
import asyncio
import sys
import os
import time

root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_path = os.path.join(root_path, 'src')
sys.path.insert(0, src_path)
sys.path.insert(0, root_path)

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient

async def test_progress():
    """Test Telethon progress callback directly."""

    api_id = int(os.getenv('UPLOADER_API_ID'))
    api_hash = os.getenv('UPLOADER_API_HASH')

    print(f"API ID: {api_id}")

    client = TelegramClient('sessions/uploader_bot', api_id, api_hash)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            print("Not authorized!")
            return

        print("Connected!")

        # Test file
        test_file = r'D:\Projects\smart-downloader\downloads\progress_test.txt'

        callback_called = [0]
        last_values = []

        def progress_callback(current, total):
            callback_called[0] += 1
            last_values.append((current, total))
            print(f"Callback #{callback_called[0]}: {current}/{total} ({current/total*100 if total > 0 else 0:.1f}%)")

        print(f"\nUploading {test_file}...")
        print(f"File size: {os.path.getsize(test_file)} bytes\n")

        # Try with file object and smaller chunk size to force progress updates
        with open(test_file, 'rb') as f:
            message = await client.send_file(
                'me',
                f,
                caption="Progress test",
                progress=progress_callback,
                part_size_kb=64  # Use smaller chunks (64KB) for more frequent updates
            )

        print(f"\nUpload complete!")
        print(f"Callback was called {callback_called[0]} times")
        print(f"Message ID: {message.id}")

    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(test_progress())
