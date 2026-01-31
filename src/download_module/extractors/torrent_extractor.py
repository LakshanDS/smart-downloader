"""
Torrent Extractor - Download Module (Stage 2)

Extract torrent info for aria2c downloads.
"""

import logging
from typing import Dict
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class TorrentExtractor(BaseExtractor):
    """Extract torrent info for aria2c"""

    async def extract(self, url: str, download_id: int) -> Dict:
        """
        Extract torrent information.

        For magnet links, return magnet URL directly.
        aria2c handles magnet downloads.

        Args:
            url: Magnet link or torrent URL
            download_id: Database download ID

        Returns:
            Dictionary with download info
        """
        logger.info(f"Extracting torrent info: {url[:50]}...")

        # For magnet links, return magnet URL directly
        # aria2c handles magnet downloads
        return {
            'download_url': url,  # magnet link
            'headers': {},
            'cookies': [],
            'title': 'Torrent',
            'file_size': None
        }
