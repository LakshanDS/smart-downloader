"""
Direct Extractor - Download Module (Stage 2)

Validate and extract info for direct file URLs.
"""

import asyncio
import logging
from typing import Dict
from urllib.parse import urlparse
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class DirectExtractor(BaseExtractor):
    """Validate direct file URLs"""

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes

    async def extract(self, url: str, download_id: int) -> Dict:
        """
        Validate direct file URL and get file info.

        Args:
            url: Direct file URL
            download_id: Database download ID

        Returns:
            Dictionary with download info
        """
        logger.info(f"Extracting direct file info: {url[:50]}...")

        # Get file info via HEAD request
        file_info = await self._get_file_info(url)

        # Validate size
        if file_info['filesize'] and file_info['filesize'] > self.MAX_FILE_SIZE:
            size_gb = file_info['filesize'] / (1024 ** 3)
            raise ValueError(f"File too large: {size_gb:.2f} GB (max: 2 GB)")

        # Sanitize filename
        clean_title = self.sanitize_title(file_info['filename'])

        logger.info(f"Direct file extraction complete: {clean_title}")

        return {
            'download_url': url,
            'headers': {},
            'cookies': [],
            'title': clean_title,
            'file_size': file_info['filesize']
        }

    async def _get_file_info(self, url: str) -> Dict:
        """
        Get file info via HEAD request.

        Args:
            url: URL to check

        Returns:
            Dictionary with file info
        """
        try:
            import aiohttp
            import ssl

            # SSL context for expired certs
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.head(url, allow_redirects=True,
                                          timeout=aiohttp.ClientTimeout(total=15)) as response:
                    content_length = response.headers.get('Content-Length')
                    content_type = response.headers.get('Content-Type', '')
                    filename = url.split('/')[-1] or 'download'

                    return {
                        'filesize': int(content_length) if content_length else None,
                        'filename': filename,
                        'content_type': content_type,
                        'url': url
                    }
        except ImportError:
            raise ImportError("aiohttp not installed")
        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            raise
