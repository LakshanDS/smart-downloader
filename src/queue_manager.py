"""
Queue Manager - Smart Downloader

Phase 3: Queue Manager Implementation
Manages the download queue for sequential processing (one-at-a-time).
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

from telegram import Bot

from config import MAX_FILE_SIZE, PROGRESS_UPDATE_INTERVAL, RETRY_DELAYS

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Queue Manager - Full Implementation

    Manages the download queue for sequential processing (one-at-a-time).
    - Sequential queue processing
    - Progress tracking (every 5 seconds)
    - Exponential backoff retry
    - File size validation
    """

    MAX_FILE_SIZE = MAX_FILE_SIZE
    RETRY_DELAYS = RETRY_DELAYS
    PROGRESS_INTERVAL = PROGRESS_UPDATE_INTERVAL

    def __init__(self, db, bot: Bot = None):
        """Initialize queue manager."""
        self.db = db
        self.bot = bot
        self.running = False
        self.current_download: Optional[dict] = None
        self.progress_message_id: Optional[int] = None
        self.progress_chat_id: Optional[int] = None

    async def start(self):
        """Start the queue processing loop."""
        logger.info("Queue Manager started")
        self.running = True

        while self.running:
            try:
                # Check if there's an active download
                active = self.db.get_active_download()

                if not active:
                    # Get next pending
                    pending = self.db.get_next_pending()

                    if pending:
                        logger.info(f"Processing download: {pending['id']}")
                        await self._process_download(pending)
                    else:
                        # No downloads, idle
                        await asyncio.sleep(5)
                else:
                    # Update progress display
                    await self._update_progress_display(active)
                    await asyncio.sleep(self.PROGRESS_INTERVAL)

            except asyncio.CancelledError:
                logger.info("Queue processor cancelled")
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}", exc_info=True)
                await asyncio.sleep(10)

        logger.info("Queue Manager stopped")

    async def stop(self):
        """Stop the queue manager."""
        logger.info("Stopping Queue Manager...")
        self.running = False

    async def add_to_queue(self, url: str, source: str, chat_id: int = None,
                          title: str = None, file_size: int = None) -> int:
        """
        Add a download to the queue.

        Args:
            url: The URL or magnet link
            source: Source type ('torrent', 'direct', 'crawler')
            chat_id: User's chat ID for progress updates
            title: Optional title for the download
            file_size: Optional file size (for validation)

        Returns:
            The queue ID, or -1 if file is too large
        """
        # Validate file size if provided
        if file_size and file_size >= self.MAX_FILE_SIZE:
            logger.warning(f"File too large: {file_size} bytes (limit: {self.MAX_FILE_SIZE})")

            # Notify user about oversized file
            if chat_id and self.bot:
                await self._notify_oversized_file(chat_id, url, title, file_size)

            # Still add to database as reference (will be skipped)
            queue_id = self.db.add_to_queue(
                url=url,
                source=source,
                title=title,
                file_size=file_size,
                chat_id=chat_id
            )

            # Mark as failed with oversized reason
            self.db.update_download_status(
                queue_id,
                'failed',
                error_message=f'File too large ({file_size / (1024**3):.2f} GB, exceeds 2GB limit)'
            )

            return -1

        queue_id = self.db.add_to_queue(
            url=url,
            source=source,
            title=title,
            file_size=file_size,
            chat_id=chat_id
        )

        logger.info(f"Added to queue: {queue_id} ({source})")
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

        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send oversized file notification: {e}")

        # Add to media library as reference (no download)
        try:
            self.db.add_media(
                title=title or url[:50],
                source_url=url,
                source_type='oversized',
                file_size=file_size
            )
        except Exception as e:
            logger.error(f"Failed to add oversized file to media: {e}")

    async def update_progress(self, download_id: int, progress: int,
                            download_speed: float = None, upload_speed: float = None,
                            eta_seconds: int = None):
        """Update download/upload progress."""
        self.db.update_progress(
            download_id=download_id,
            progress=progress,
            download_speed=download_speed,
            upload_speed=upload_speed,
            eta_seconds=eta_seconds
        )

    async def mark_completed(self, download_id: int):
        """Mark download as completed."""
        self.db.update_download_status(download_id, 'completed')
        logger.info(f"Download completed: {download_id}")

    async def mark_failed(self, download_id: int, error_message: str):
        """Mark download as failed."""
        self.db.update_download_status(
            download_id=download_id,
            status='failed',
            error_message=error_message
        )
        logger.error(f"Download failed: {download_id} - {error_message}")

    async def _process_download(self, download: dict):
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
                # Note: Handlers will be implemented in Phase 4-6
                if source == 'torrent':
                    # Placeholder for Phase 4
                    logger.info(f"Torrent handler for {download_id}")
                    raise NotImplementedError("Torrent handler not implemented yet (Phase 4)")
                elif source == 'direct':
                    # Placeholder for Phase 5
                    logger.info(f"Direct handler for {download_id}")
                    raise NotImplementedError("Direct handler not implemented yet (Phase 5)")
                elif source == 'crawler':
                    # Placeholder for Phase 6
                    logger.info(f"Crawler handler for {download_id}")
                    raise NotImplementedError("Crawler handler not implemented yet (Phase 6)")
                else:
                    raise ValueError(f"Unknown source: {source}")

            except Exception as e:
                logger.error(f"Download {download_id} failed (attempt {retry_count + 1}): {e}")

                retry_count = self.db.increment_retry(download_id)

                if retry_count > len(self.RETRY_DELAYS):
                    # Give up
                    error_msg = f"Failed after {len(self.RETRY_DELAYS)} retries: {str(e)}"
                    await self.mark_failed(download_id, error_msg)
                    await self._send_failure_message(chat_id, download, error_msg)
                    await self._delete_progress_message()
                    return

                # Wait before retry
                delay = self.RETRY_DELAYS[retry_count - 1]
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

    async def _send_progress_message(self, chat_id: int, download: dict) -> int:
        """Send initial progress message."""
        queue_summary = self.db.get_queue_summary()

        message = f"""
📥 **Active Downloads:**
━━━━━━━━━━━━━━━━━━━━━
Items in queue: {queue_summary['pending'] + 1}

Downloading 1/{queue_summary['pending'] + 1}:
📹 {download['title'] or 'Processing...'}
[░░░░░░░░░░░░░░░] 0%
⏱️ ETA: Calculating...
↓ 0.00 MB/s | ↑ 0.00 MB/s
        """

        msg = await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        return msg.message_id

    async def _update_progress_display(self, download: dict):
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
                text=message,
                parse_mode='Markdown'
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

    async def _send_completion_message(self, chat_id: int, download: dict):
        """Send completion message."""
        message = f"""
✅ **Download Complete:** {download['title']}

🎬 Ready to play!

[Deleting this message in 60s...]
        """
        msg = await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        # Auto-delete after 60s
        await asyncio.sleep(60)
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            pass

    async def _send_failure_message(self, chat_id: int, download: dict, error: str):
        """Send failure notification."""
        message = f"""
❌ **Download Failed:** {download['title']}

Error: {error}

Retried {len(self.RETRY_DELAYS)} times. Giving up.
        """
        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send failure message: {e}")
