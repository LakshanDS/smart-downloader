"""
Base Extractor - Download Module (Stage 2)

Base class for all URL extractors.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Base class for URL extractors"""

    def __init__(self, db):
        """
        Initialize extractor.

        Args:
            db: Database manager instance
        """
        self.db = db

    @abstractmethod
    async def extract(self, url: str, download_id: int) -> Dict:
        """
        Extract download URL and metadata.

        Args:
            url: URL to extract from
            download_id: Database download ID

        Returns:
            Dictionary with:
                'download_url': str,      # Actual download URL
                'headers': Dict,         # HTTP headers
                'cookies': List,          # Cookies
                'title': str,            # File title
                'file_size': int         # File size in bytes
        """
        pass

    def sanitize_title(self, title: str, max_length: int = 100) -> str:
        """
        Clean title for use as filename.

        Args:
            title: Raw title string
            max_length: Maximum filename length

        Returns:
            Sanitized filename (without extension)
        """
        import re

        if not title:
            return "download"

        # Remove emojis and non-ASCII
        cleaned = re.sub(r'[^\x00-\x7F]+', '', title)

        # Keep only alphanumeric, spaces, hyphens, underscores
        cleaned = re.sub(r'[^a-zA-Z0-9\s\-_]', '', cleaned)

        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Trim and limit length
        cleaned = cleaned.strip().title()

        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].strip()

        return cleaned or "download"
