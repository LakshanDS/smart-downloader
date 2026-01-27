# Phase 3: Queue Manager

**Objective:** Manage sequential download queue with one-at-a-time processing, progress tracking, and automatic retry logic.

## Architecture

```
User sends link(s)
       │
       ↓ Bot validates ownership
       ↓
┌────────────────────────────────────┐
│  Add to Queue (SQLite)            │
│  - Store URL with status=pending  │
│  - Pre-validate file size         │
│  - Extract metadata (title)       │
└────────────────────────────────────┘
       │
       ↓ Background processor
┌────────────────────────────────────┐
│  Queue Processor                  │
│  - Get next pending (FIFO)        │
│  - Mark as downloading            │
│  - Route to appropriate handler    │
│  - Update progress (5s intervals)  │
│  - On completion: upload → next   │
│  - On failure: retry 3x           │
└────────────────────────────────────┘
```

## Key Features

- **Sequential processing**: One download at a time
- **Progress display**: Single summary message updated every 5 seconds
- **Exponential backoff retry**: 0s → 2min → 8min → failed
- **File size validation**: Pre-check before download (<2GB)
- **Speed tracking**: Download and upload speeds with ETA

## Components

### 1. Queue Manager (`queue_manager.py`)

```python
import asyncio
import logging
from typing import Optional, Dict, Callable
from datetime import datetime, timedelta
from database import DatabaseManager

logger = logging.getLogger(__name__)

class QueueManager:
    """Manage download queue with sequential processing."""

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes
    RETRY_DELAYS = [0, 120, 480]  # 0s, 2min, 8min in seconds

    def __init__(self, db: DatabaseManager, bot=None):
        self.db = db
        self.bot = bot
        self.running = False
        self.current_task: Optional[asyncio.Task] = None
        self.progress_message_id: Optional[int] = None
        self.progress_chat_id: Optional[int] = None

    async def add_to_queue(self, url: str, source: str, chat_id: int,
                          title: str = None, file_size: int = None) -> int:
        """Add download to queue."""
        # Validate file size if provided
        if file_size and file_size > self.MAX_FILE_SIZE:
            logger.warning(f"File too large: {file_size} bytes")
            # Still add to queue but mark for user notification
            await self._notify_oversized_file(chat_id, url, title, file_size)
            return -1

        queue_id = self.db.add_to_queue(
            url=url,
            source=source,
            title=title,
            file_size=file_size,
            chat_id=chat_id
        )

        logger.info(f"Added to queue: {url} (ID: {queue_id})")
        return queue_id

    async def _notify_oversized_file(self, chat_id: int, url: str,
                                     title: str, file_size: int):
        """Notify user about oversized file."""
        size_gb = file_size / (1024 ** 3)
        message = f"""
⚠️ **File Too Large**

📹 {title or 'Unknown'}
📏 Size: {size_gb:.2f} GB
↳ Telegram limit: 2 GB per file

Skipped. Added to library for reference.
        """

        if self.bot:
            await self.bot.send_message(chat_id=chat_id, text=message)

        # Add to media library as reference (no download)
        self.db.add_media(
            title=title or url[:50],
            category='custom',
            source_url=url,
            source_type='oversized',
            file_size=file_size
        )

    async def start(self):
        """Start background queue processor."""
        if self.running:
            logger.warning("Queue manager already running")
            return

        self.running = True
        logger.info("Starting queue processor...")

        while self.running:
            try:
                # Check if there's an active download
                active = self.db.get_active_download()

                if not active:
                    # Get next pending
                    pending = self.db.get_next_pending()

                    if pending:
                        await self._process_download(pending)
                    else:
                        # No downloads, idle
                        await asyncio.sleep(5)
                else:
                    # Update progress display
                    await self._update_progress_display(active)
                    await asyncio.sleep(5)

            except asyncio.CancelledError:
                logger.info("Queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"Queue processor error: {e}", exc_info=True)
                await asyncio.sleep(10)

        logger.info("Queue processor stopped")

    def stop(self):
        """Stop queue processor."""
        self.running = False
        if self.current_task:
            self.current_task.cancel()

    async def _process_download(self, download: Dict):
        """Process a single download with retry logic."""
        download_id = download['id']
        url = download['url']
        source = download['source']
        chat_id = download['chat_id']

        logger.info(f"Processing download {download_id}: {url}")

        # Store progress message info
        self.progress_chat_id = chat_id

        # Send initial progress message
        self.progress_message_id = await self._send_progress_message(chat_id, download)

        retry_count = 0

        while retry_count <= len(self.RETRY_DELAYS):
            try:
                # Mark as downloading
                self.db.update_download_status(download_id, 'downloading')

                # Route to appropriate handler
                if source == 'torrent':
                    from torrent_handler import TorrentHandler
                    handler = TorrentHandler(self.db)
                    file_path = await handler.download(url)
                elif source == 'direct':
                    from direct_handler import DirectHandler
                    handler = DirectHandler(self.db)
                    file_path = await handler.download(url)
                elif source == 'crawler':
                    from crawler_handler import CrawlerHandler
                    handler = CrawlerHandler(self.db)
                    file_path = await handler.download(url)
                else:
                    raise ValueError(f"Unknown source: {source}")

                # Download successful, now upload
                await self._upload_to_telegram(download_id, file_path)

                # Mark complete
                self.db.update_download_status(download_id, 'completed')
                await self._delete_progress_message()
                await self._send_completion_message(chat_id, download)

                logger.info(f"Download {download_id} completed successfully")
                return

            except Exception as e:
                logger.error(f"Download {download_id} failed (attempt {retry_count + 1}): {e}")

                retry_count = self.db.increment_retry(download_id)

                if retry_count > len(self.RETRY_DELAYS):
                    # Give up
                    self.db.update_download_status(
                        download_id, 'failed',
                        error_message=str(e)
                    )
                    await self._send_failure_message(chat_id, download, str(e))
                    await self._delete_progress_message()
                    return

                # Wait before retry
                delay = self.RETRY_DELAYS[retry_count - 1]
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

    async def _upload_to_telegram(self, download_id: int, file_path: str):
        """Upload file to Telegram via userbot."""
        from uploader_bot import UploaderBot

        self.db.update_download_status(download_id, 'uploading')

        try:
            uploader = UploaderBot()
            result = await uploader.upload(file_path)

            # Update media with file_id
            download = self.db.get_active_download()
            media_id = self.db.add_media(
                title=download['title'],
                category='custom',  # Will be updated by user
                source_url=download['url'],
                source_type=download['source'],
                file_size=download['file_size'],
                file_id=result['file_id'],
                hash=result.get('hash')
            )

            logger.info(f"Upload complete: {result['file_id']}")

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            # Upload retry uses same logic as download retry
            raise

    async def _send_progress_message(self, chat_id: int, download: Dict) -> int:
        """Send initial progress message."""
        queue_summary = self.db.get_queue_summary()

        message = f"""
📥 **Active Downloads:**
━━━━━━━━━━━━━━━━━━━━━
Items in queue: {queue_summary['pending'] + 1}

Downloading 1/{queue_summary['pending'] + 1}:
📹 {download['title'] or 'Processing...'}
[░░░░░░░░░░░░░░░░] 0%
⏱️ ETA: Calculating...
↓ 0.00 MB/s | ↑ 0.00 MB/s
        """

        msg = await self.bot.send_message(chat_id=chat_id, text=message)
        self.db.update_download_status(
            download['id'], 'downloading'
        )
        return msg.message_id

    async def _update_progress_display(self, download: Dict):
        """Edit progress message with current status."""
        if not self.progress_message_id or not self.progress_chat_id:
            return

        queue_summary = self.db.get_queue_summary()
        progress = download['progress']
        dl_speed = download.get('download_speed', 0) or 0
        ul_speed = download.get('upload_speed', 0) or 0
        eta = download.get('eta_seconds', 0) or 0

        # Progress bar
        filled = int(20 * progress / 100)
        bar = '█' * filled + '░' * (20 - filled)

        # Format speeds
        dl_str = f"{dl_speed:.2f} MB/s" if dl_speed else "0.00 MB/s"
        ul_str = f"{ul_speed:.2f} MB/s" if ul_speed else "0.00 MB/s"

        # Format ETA
        if eta > 0:
            eta_mins = eta // 60
            eta_secs = eta % 60
            eta_str = f"{eta_mins}m {eta_secs}s"
        else:
            eta_str = "Calculating..."

        # Status text
        status_text = "Downloading" if download['status'] == 'downloading' else "Uploading"

        message = f"""
📥 **Active Downloads:**
━━━━━━━━━━━━━━━━━━━━━
Items in queue: {queue_summary['pending']}

{status_text} 1/{queue_summary['pending'] + 1}:
📹 {download['title'] or 'Processing...'}
[{bar}] {progress}%
⏱️ ETA: {eta_str}
↓ {dl_str} | ↑ {ul_str}
        """

        try:
            await self.bot.edit_message_text(
                chat_id=self.progress_chat_id,
                message_id=self.progress_message_id,
                text=message
            )
        except Exception as e:
            logger.warning(f"Failed to update progress message: {e}")

    async def _delete_progress_message(self):
        """Delete progress message after completion."""
        if self.progress_message_id and self.progress_chat_id:
            try:
                # Wait 60 seconds before deleting
                await asyncio.sleep(60)
                await self.bot.delete_message(
                    chat_id=self.progress_chat_id,
                    message_id=self.progress_message_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete progress message: {e}")
            finally:
                self.progress_message_id = None
                self.progress_chat_id = None

    async def _send_completion_message(self, chat_id: int, download: Dict):
        """Send completion message."""
        message = f"""
✅ **Download Complete:** {download['title']}

🎬 Ready to play!

[Deleting this message in 60s...]
        """
        msg = await self.bot.send_message(chat_id=chat_id, text=message)

        # Auto-delete after 60s
        await asyncio.sleep(60)
        await self.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)

    async def _send_failure_message(self, chat_id: int, download: Dict, error: str):
        """Send failure notification."""
        message = f"""
❌ **Download Failed:** {download['title']}

Error: {error}

Retried 3 times. Giving up.
        """
        await self.bot.send_message(chat_id=chat_id, text=message)
```

### 2. Integration with Bot

```python
# In bot.py
from queue_manager import QueueManager

queue_manager = QueueManager(db=db, bot=bot)

async def handle_download(update: Update, context):
    """Handle /download command."""
    if not db.is_authorized(update.effective_chat.id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    url = context.args[0] if context.args else None
    if not url:
        await update.message.reply_text("Usage: /download <url>")
        return

    # Detect source type
    source = detect_source_type(url)

    # Delete user's message
    await update.message.delete()

    # Add to queue
    queue_id = await queue_manager.add_to_queue(
        url=url,
        source=source,
        chat_id=update.effective_chat.id
    )

    queue_summary = db.get_queue_summary()

    await update.message.reply_text(
        f"✅ Added to queue!\n\n"
        f"Position in queue: {queue_summary['pending']}\n"
        f"I'll start processing shortly..."
    )

async def handle_torrent(update: Update, context):
    """Handle /torrent command."""
    if not db.is_authorized(update.effective_chat.id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    magnet = context.args[0] if context.args else None
    if not magnet or not magnet.startswith('magnet:?'):
        await update.message.reply_text("Usage: /torrent <magnet_link>")
        return

    # Delete user's message
    await update.message.delete()

    # Add to queue
    await queue_manager.add_to_queue(
        url=magnet,
        source='torrent',
        chat_id=update.effective_chat.id
    )

    await update.message.reply_text("✅ Torrent added to queue!")

# Start queue processor in background
async def main():
    # ... bot setup ...

    # Start queue manager
    asyncio.create_task(queue_manager.start())

    # Run bot
    await app.run_polling()
```

## Configuration

```python
# config.py
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
PROGRESS_UPDATE_INTERVAL = 5  # seconds
PROGRESS_MESSAGE_AUTO_DELETE = 60  # seconds
RETRY_DELAYS = [0, 120, 480]  # exponential: 0s, 2min, 8min
```

## Implementation Tasks

- [ ] Create `queue_manager.py` with QueueManager class
- [ ] Implement FIFO queue processing
- [ ] Add progress message updates (5s intervals)
- [ ] Implement exponential backoff retry logic
- [ ] Add file size validation (<2GB)
- [ ] Implement oversized file notification
- [ ] Add speed tracking and ETA calculation
- [ ] Test with multiple queued downloads
- [ ] Test retry behavior with simulated failures
- [ ] Integrate with bot command handlers

## Dependencies

```python
# No additional dependencies (uses database.py)
```

## Notes

- **Sequential**: Only one download at a time
- **Progress display**: Single message edited every 5 seconds
- **Retry logic**: 3 attempts with exponential backoff
- **File size**: Pre-validate, notify user if >2GB
- **Auto-cleanup**: Delete progress messages 60s after completion
