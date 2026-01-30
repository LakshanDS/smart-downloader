"""
Upload Pooler - Upload Module

Non-blocking pooler for uploads.
Watches database for completed downloads and uploads them to Telegram.
"""

import asyncio
import logging
import signal
from typing import Optional, Dict

from upload_module.upload_manager import UploadManager

logger = logging.getLogger(__name__)


class UploadPooler:
    """
    Upload Pooler - Separate Process for Uploads

    Non-blocking upload system that:
    - Polls database for completed downloads (status='downloaded')
    - Uploads files to Telegram via userbot
    - Handles retries with exponential backoff
    - Supports graceful shutdown

    Status flow: downloaded -> uploading -> uploaded
    """

    def __init__(self, db, download_dir: str = None,
                 userbot_api_id: str = None, userbot_api_hash: str = None,
                 userbot_phone: str = None):
        """
        Initialize upload pooler.

        Args:
            db: Database manager instance
            download_dir: Directory where downloaded files are stored
            userbot_api_id: Telegram API ID for userbot
            userbot_api_hash: Telegram API hash for userbot
            userbot_phone: Phone number for userbot
        """
        self.db = db
        self.download_dir = download_dir or './downloads'

        # State tracking
        self.running = True
        self.current_upload_id: Optional[int] = None
        self.shutdown_event = asyncio.Event()

        # Initialize upload manager (uploader created inside)
        self.upload_manager = UploadManager(
            db=db,
            download_dir=self.download_dir,
            uploader=None  # Will create from env vars
        )

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info("UploadPooler initialized")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals for graceful cleanup."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
        self.shutdown_event.set()

    async def start(self, poll_interval: int = 3):
        """
        Main pooler loop.

        Args:
            poll_interval: Database poll interval in seconds
        """
        logger.info("UploadPooler started")

        # Start upload manager processor
        await self.upload_manager.start_processor(check_interval=poll_interval)

        # Keep running until shutdown
        while self.running:
            try:
                # Check for shutdown signal
                if self.shutdown_event.is_set():
                    logger.info("Shutdown event received, stopping pooler...")
                    break

                # Sleep briefly
                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                logger.info("Pooler cancelled")
                break
            except Exception as e:
                logger.error(f"Pooler loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

        # Graceful shutdown
        await self._shutdown()

    async def _shutdown(self):
        """Graceful shutdown - wait for current upload to complete."""
        logger.info("Initiating graceful shutdown...")

        # Wait for current upload to complete (no timeout - uploads should finish)
        status = self.upload_manager.get_status()
        if status.get('uploading'):
            logger.info("Waiting for current upload to complete...")
            while self.upload_manager.uploading:
                await asyncio.sleep(1)

        # Stop upload manager
        await self.upload_manager.stop_processor()

        # Disconnect uploader
        await self.upload_manager.disconnect()

        logger.info("UploadPooler shutdown complete")

    def get_status(self) -> Dict:
        """Get current pooler status."""
        manager_status = self.upload_manager.get_status()
        return {
            'running': self.running,
            'current_upload_id': self.current_upload_id,
            **manager_status
        }
