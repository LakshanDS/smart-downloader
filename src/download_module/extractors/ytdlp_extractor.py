"""
yt-dlp Extractor - Download Module (Stage 2)

Extract direct URL using yt-dlp for supported sites.
"""

import asyncio
import logging
from typing import Dict
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class YtdlpExtractor(BaseExtractor):
    """Extract direct URL using yt-dlp"""

    async def extract(self, url: str, download_id: int) -> Dict:
        """
        Extract download URL and metadata using yt-dlp.

        Args:
            url: URL to extract from
            download_id: Database download ID

        Returns:
            Dictionary with download info
        """
        logger.info(f"Extracting yt-dlp info: {url[:50]}...")

        try:
            import yt_dlp
        except ImportError:
            raise ImportError("yt-dlp not installed")

        # Run yt-dlp in thread to avoid blocking
        loop = asyncio.get_event_loop()

        def _extract():
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'best',  # Get best quality direct URL
                'extract_flat': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Get the direct download URL
                if 'requested_formats' in info:
                    # Merged video+audio
                    format_info = info['requested_formats'][0]
                elif 'url' in info:
                    format_info = info
                else:
                    # Find best format
                    format_info = info.get('formats', [{}])[0]

                # Extract headers
                headers = format_info.get('http_headers', {})

                # Extract cookies (if any)
                cookies = ydl.cookiejar.get_cookies_for_url(url)

                return format_info, headers, cookies, info

        format_info, headers, cookies, info = await loop.run_in_executor(None, _extract)

        download_url = format_info.get('url')
        title = info.get('title', 'video')
        ext = format_info.get('ext', 'mp4')

        # Sanitize title
        clean_title = self.sanitize_title(title)

        logger.info(f"yt-dlp extraction complete: {clean_title}.{ext}")

        return {
            'download_url': download_url,
            'headers': headers,
            'cookies': cookies,
            'title': clean_title,
            'file_size': format_info.get('filesize')
        }
