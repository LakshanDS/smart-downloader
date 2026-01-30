"""
Upload Manager - Upload Module
Watches database for completed downloads and uploads them to Telegram.
Separate module from download system, uses database as middleman.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Dict
from datetime import datetime

from upload_module.uploader_bot import UploaderBot, UploadError

logger = logging.getLogger(__name__)


class UploadManager:
    """
    Manage file uploads by watching database.

    Flow:
    1. Watch DB for status='downloaded'
    2. Verify file exists in download directory
    3. Upload via userbot to Telegram
    4. Save file_id to DB
    5. Delete local file
    6. Update status to 'uploaded' or 'failed'
    """

    MAX_RETRIES = 3
    PROGRESS_UPDATE_INTERVAL = 3  # seconds

    def __init__(self, db=None, download_dir: str = None, uploader: UploaderBot = None):
        """
        Initialize upload manager.

        Args:
            db: DatabaseManager instance
            download_dir: Directory where downloaded files are stored
            uploader: Optional UploaderBot instance (creates new if None)
        """
        self.db = db
        self.download_dir = download_dir or os.path.abspath('./downloads')
        self.uploader = uploader or UploaderBot()

        self.uploading: bool = False
        self.current_task = None
        self._stop_event = asyncio.Event()
        self._last_progress_update = 0
        self._upload_start_bytes = 0
        self._upload_start_time = 0

    def get_file_path(self, filename: str) -> str:
        """Get full file path in download directory."""
        return os.path.join(self.download_dir, filename)

    def verify_file(self, file_path: str, expected_size: int = None) -> bool:
        """
        Verify file exists and optionally check size.

        Args:
            file_path: Path to file
            expected_size: Expected file size in bytes

        Returns:
            True if file exists and size matches
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False

        if expected_size is not None:
            actual_size = os.path.getsize(file_path)
            if actual_size != expected_size:
                logger.warning(
                    f"File size mismatch: expected {expected_size}, got {actual_size}"
                )
                # Still allow upload, just log warning

        return True

    def _make_progress_callback(self, download_id: int, total_bytes: int):
        """
        Create a progress callback for Telethon upload.

        Args:
            download_id: Database download ID
            total_bytes: Total file size in bytes

        Returns:
            Callback function(current, total)
        """
        # Store previous bytes to calculate speed
        previous_bytes = [0]
        previous_time = [time.time()]

        def callback(current: int, total: int):
            nonlocal previous_bytes, previous_time
            now = time.time()

            # Log callback invocation for debugging
            logger.debug(f"Progress callback: current={current}, total={total}")

            # Throttle updates to every 3 seconds
            if now - self._last_progress_update < self.PROGRESS_UPDATE_INTERVAL:
                return

            # Calculate progress
            if total > 0:
                progress = int((current / total) * 100)
            else:
                progress = 0

            # Calculate upload speed (bytes per second)
            time_delta = now - previous_time[0]
            bytes_delta = current - previous_bytes[0]

            if time_delta > 0 and bytes_delta >= 0:
                speed = bytes_delta / time_delta
            else:
                # Fallback to overall speed
                elapsed = now - self._upload_start_time
                if elapsed > 0 and current > 0:
                    speed = current / elapsed
                else:
                    speed = 0

            # Calculate ETA
            remaining = total_bytes - current
            if speed > 0:
                eta = int(remaining / speed)
            else:
                eta = None

            # Update database
            try:
                self.db.update_progress(
                    download_id,
                    progress,
                    upload_speed=speed,
                    eta_seconds=eta
                )
                logger.info(f"Upload progress: {progress}% ({speed/1024/1024:.2f} MB/s, ETA: {eta}s")
            except Exception as e:
                logger.error(f"Failed to update progress: {e}")

            # Update tracking
            previous_bytes[0] = current
            previous_time[0] = now
            self._last_progress_update = now

        return callback

    async def _upload_single(self, download: Dict) -> bool:
        """
        Upload a single download item.

        Args:
            download: Download dict from database

        Returns:
            True if successful
        """
        download_id = download['id']
        file_path = download.get('file_path') or self.get_file_path(
            download.get('title', 'download')
        )

        logger.info(f"Starting upload for download {download_id}: {file_path}")

        # Verify file exists
        if not self.verify_file(file_path, download.get('file_size')):
            await self._mark_failed(download_id, "File not found or size mismatch")
            return False

        # Update status to uploading
        self.db.update_download_status(download_id, 'uploading')
        self.db.update_progress(download_id, 0)

        # Reset progress tracking
        self._upload_start_time = time.time()
        self._last_progress_update = 0

        # Create caption from title
        caption = download.get('title', '')

        # Log progress callback creation
        logger.info(f"Creating progress callback for {download_id}")

        try:
            # Get file size for progress callback
            file_size = os.path.getsize(file_path)

            # Upload with progress callback
            result = await self.uploader.upload_file(
                file_path,
                caption=caption,
                progress_callback=self._make_progress_callback(
                    download_id,
                    file_size
                )
            )

            if not result or not result.get('file_id'):
                raise UploadError("Upload failed: no file_id returned")

            # Save file_id to database
            self.db.update_download_file_id(
                download_id,
                result['file_id'],
                file_path
            )

            # Update progress to 100%
            self.db.update_progress(download_id, 100)

            logger.info(f"Upload complete: {file_path} -> file_id={result['file_id']}")

            # Delete local file
            try:
                os.remove(file_path)
                logger.info(f"Deleted local file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete local file: {e}")

            return True

        except UploadError as e:
            logger.error(f"Upload error for {file_path}: {e}")
            await self._mark_failed(download_id, str(e))

            # Delete failed file
            try:
                os.remove(file_path)
                logger.info(f"Deleted failed file: {file_path}")
            except Exception:
                pass

            return False

        except Exception as e:
            logger.error(f"Unexpected error uploading {file_path}: {e}")
            await self._mark_failed(download_id, f"Unexpected error: {str(e)}")

            # Delete failed file
            try:
                os.remove(file_path)
            except Exception:
                pass

            return False

    async def _mark_failed(self, download_id: int, error: str):
        """Mark download as failed in database."""
        try:
            self.db.update_download_status(download_id, 'failed', error_message=error)
            logger.warning(f"Marked download {download_id} as failed: {error}")
        except Exception as e:
            logger.error(f"Failed to mark download {download_id} as failed: {e}")

    async def process_queue(self):
        """
        Process all completed downloads waiting for upload.

        Runs sequentially, one upload at a time.
        """
        if self.uploading:
            logger.debug("Upload already in progress")
            return

        self.uploading = True
        logger.info("Starting upload queue processing...")

        while not self._stop_event.is_set():
            # Get next completed download
            download = self.db.get_next_completed_upload()

            if not download:
                logger.debug("No downloads waiting for upload")
                break

            # Upload with retries
            success = False
            last_error = None

            for attempt in range(self.MAX_RETRIES):
                try:
                    logger.info(f"Upload attempt {attempt + 1}/{self.MAX_RETRIES}")
                    success = await self._upload_single(download)

                    if success:
                        break

                    last_error = f"Attempt {attempt + 1} failed"

                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Upload attempt {attempt + 1} error: {e}")

                # Wait before retry (exponential backoff)
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = 2 ** attempt * 60  # 1min, 2min, 4min
                    logger.info(f"Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)

            if not success:
                logger.error(f"Upload failed after {self.MAX_RETRIES} attempts: {last_error}")

            # Small delay between uploads
            if not self._stop_event.is_set():
                await asyncio.sleep(2)

        self.uploading = False
        logger.info("Upload queue processing complete")

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
            'uploading': self.uploading,
            'uploader_status': self.uploader.get_status(),
            'processor_running': self.current_task is not None
        }

    async def disconnect(self):
        """Disconnect uploader bot."""
        await self.uploader.disconnect()
