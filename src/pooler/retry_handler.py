"""
Retry Handler - Smart Downloader Pooler

Handle download failures with exponential backoff retry logic.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class RetryHandler:
    """
    Retry Handler - Exponential Backoff

    Handles download failures with configurable retry logic:
    - Max retries: 3
    - Base delay: 60 seconds
    - Exponential backoff: 60s, 120s, 240s
    """

    MAX_RETRIES = 3
    BASE_DELAY = 60  # seconds

    def __init__(self, db):
        """
        Initialize retry handler.

        Args:
            db: Database manager instance
        """
        self.db = db

    async def handle_failure(self, download_id: int, error: str) -> bool:
        """
        Handle download failure with retry logic.

        Args:
            download_id: Database download ID
            error: Error message

        Returns:
            True if will retry, False if giving up
        """
        retry_count = self.db.increment_retry(download_id)
        logger.info(f"Download {download_id} failed (attempt {retry_count}/{self.MAX_RETRIES}): {error}")

        if retry_count < self.MAX_RETRIES:
            # Calculate exponential backoff delay
            delay = self.BASE_DELAY * (2 ** retry_count)
            logger.info(f"Retrying download {download_id} in {delay}s...")

            # Wait before retry
            await asyncio.sleep(delay)

            # Reset to pending for retry
            self.db.update_download_status(download_id, 'pending')
            return True
        else:
            # Max retries reached, mark as failed
            self.db.update_download_status(download_id, 'failed', error)
            logger.error(f"Download {download_id} failed after {self.MAX_RETRIES} retries")
            return False

    def get_max_retries(self) -> int:
        """Get maximum retry count."""
        return self.MAX_RETRIES

    def get_base_delay(self) -> int:
        """Get base retry delay in seconds."""
        return self.BASE_DELAY
