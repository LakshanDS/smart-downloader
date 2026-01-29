"""
Upload Manager - Phase 8
Manage file uploads via userbot with queue processing.
"""

import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime

from uploader_bot import UploaderBot, UploadError

logger = logging.getLogger(__name__)


class UploadManager:
    """Manage file uploads via userbot."""

    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None,
                 phone: Optional[str] = None, db=None):
        """
        Initialize upload manager.

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            phone: Phone number for userbot
            db: Optional DatabaseManager for updating media records
        """
        self.uploader = UploaderBot(api_id, api_hash, phone)
        self.db = db
        self.queue: List[Dict] = []
        self.uploading: bool = False
        self.current_task = None
        self._stop_event = asyncio.Event()

    def queue_upload(self, file_path: str, media_id: int, caption: Optional[str] = None) -> bool:
        """
        Add file to upload queue.

        Args:
            file_path: Path to file to upload
            media_id: Media ID in database
            caption: Optional caption

        Returns:
            True if queued successfully
        """
        if not file_path or not media_id:
            logger.error("Invalid upload request: file_path and media_id required")
            return False

        self.queue.append({
            'file_path': file_path,
            'media_id': media_id,
            'caption': caption,
            'queued_at': datetime.now().isoformat()
        })

        logger.info(f"Queued upload: {file_path} (media_id={media_id})")
        return True

    def queue_uploads(self, uploads: List[Dict]) -> int:
        """
        Add multiple files to upload queue.

        Args:
            uploads: List of dicts with 'file_path', 'media_id', 'caption'

        Returns:
            Number of uploads queued
        """
        count = 0
        for upload in uploads:
            if self.queue_upload(
                upload.get('file_path'),
                upload.get('media_id'),
                upload.get('caption')
            ):
                count += 1

        logger.info(f"Queued {count} uploads")
        return count

    async def process_queue(self):
        """Process all queued uploads sequentially."""
        if self.uploading or not self.queue:
            return

        self.uploading = True
        logger.info(f"Processing {len(self.queue)} queued uploads...")

        while self.queue and not self._stop_event.is_set():
            item = self.queue.pop(0)

            try:
                # Upload to userbot
                result = await self._upload_item(item)

                if result:
                    # Update database with file_id
                    await self._update_database(item['media_id'], result)

                    logger.info(f"Upload complete: {item['file_path']}")
                else:
                    # Mark as failed
                    await self._mark_failed(item['media_id'], "Upload failed")

            except UploadError as e:
                logger.error(f"Upload error for {item['file_path']}: {e}")
                await self._mark_failed(item['media_id'], str(e))

            except Exception as e:
                logger.error(f"Unexpected error uploading {item['file_path']}: {e}")
                await self._mark_failed(item['media_id'], f"Unexpected error: {str(e)}")

            # Small delay between uploads
            if self.queue:
                await asyncio.sleep(2)

        self.uploading = False
        logger.info("Upload queue processed")

    async def _upload_item(self, item: Dict) -> Optional[Dict]:
        """
        Upload a single item.

        Args:
            item: Upload queue item

        Returns:
            File metadata dict or None
        """
        file_path = item['file_path']

        # Check file exists
        import os
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        # Upload using uploader bot
        result = self.uploader.upload_file(
            file_path,
            caption=item.get('caption')
        )

        return result

    async def _update_database(self, media_id: int, file_metadata: Dict):
        """
        Update database with file_id after upload.

        Args:
            media_id: Media ID in database
            file_metadata: File metadata from upload
        """
        if not self.db:
            return

        try:
            # Update media with userbot file_id
            self.db.update_media_file_id(
                media_id,
                file_metadata['message_id'],
                file_metadata.get('file_id'),
                file_metadata.get('file_size'),
                file_metadata.get('file_name'),
                file_metadata.get('duration')
            )

            logger.info(f"Updated media {media_id} with file_id")

        except Exception as e:
            logger.error(f"Failed to update database for media {media_id}: {e}")

    async def _mark_failed(self, media_id: int, error: str):
        """
        Mark media as failed in database.

        Args:
            media_id: Media ID in database
            error: Error message
        """
        if not self.db:
            return

        try:
            # Update media status to failed
            self.db.update_media_status(media_id, 'failed', error)
            logger.warning(f"Marked media {media_id} as failed: {error}")

        except Exception as e:
            logger.error(f"Failed to mark media {media_id} as failed: {e}")

    async def start_processor(self, check_interval: int = 5):
        """
        Start background upload processor.

        Args:
            check_interval: Check interval in seconds
        """
        if self.current_task:
            logger.warning("Upload processor already running")
            return

        logger.info(f"Starting upload processor (checks every {check_interval}s)")

        async def processor_loop():
            while not self._stop_event.is_set():
                try:
                    await self.process_queue()
                    await asyncio.sleep(check_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Upload processor error: {e}")
                    await asyncio.sleep(10)

        self.current_task = asyncio.create_task(processor_loop())

    async def stop_processor(self):
        """Stop upload processor."""
        self._stop_event.set()

        if self.current_task:
            self.current_task.cancel()
            try:
                await self.current_task
            except asyncio.CancelledError:
                pass

        self.uploading = False
        logger.info("Upload processor stopped")

    def get_status(self) -> Dict:
        """
        Get current upload status.

        Returns:
            Dictionary with status info
        """
        return {
            'queue_size': len(self.queue),
            'uploading': self.uploading,
            'uploader_status': self.uploader.get_status(),
            'processor_running': self.current_task is not None
        }

    def get_queue(self) -> List[Dict]:
        """
        Get current upload queue.

        Returns:
            List of queued uploads
        """
        return self.queue.copy()

    def clear_queue(self) -> int:
        """
        Clear upload queue.

        Returns:
            Number of items cleared
        """
        count = len(self.queue)
        self.queue.clear()
        logger.info(f"Cleared {count} items from upload queue")
        return count

    def disconnect(self):
        """Disconnect uploader bot."""
        self.uploader.disconnect()
