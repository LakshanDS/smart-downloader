"""
Cancel Manager - Download Module

Handle cancel logic for downloads.
"""

import logging

logger = logging.getLogger(__name__)


class CancelManager:
    """Handle cancel logic for downloads"""

    @staticmethod
    def check_and_handle_cancel(download_id: int, db) -> bool:
        """
        Check if download should be cancelled and handle it.

        Args:
            download_id: Database download ID
            db: Database manager instance

        Returns:
            True if cancelled, False if should continue
        """
        download = db.get_download(download_id)

        if download and download.get('cancelled', False):
            logger.info(f"Download {download_id} cancelled")
            return True

        return False

    @staticmethod
    def cancel_download(download_id: int, db):
        """
        Mark download as cancelled in database.

        Args:
            download_id: Database download ID
            db: Database manager instance
        """
        db.update_download_status(download_id, 'cancelled')
        logger.info(f"Marked download {download_id} as cancelled")
