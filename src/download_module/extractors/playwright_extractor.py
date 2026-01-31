"""
Playwright Extractor - Download Module (Stage 2)

Extract video URL using Playwright crawler.
"""

import asyncio
import logging
from typing import Dict
from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)


class PlaywrightExtractor(BaseExtractor):
    """Extract video URL using Playwright crawler"""

    async def extract(self, url: str, download_id: int) -> Dict:
        """
        Extract video URL using Playwright crawler.

        Args:
            url: URL to extract from
            download_id: Database download ID

        Returns:
            Dictionary with download info
        """
        logger.info(f"Extracting Playwright video: {url[:50]}...")

        # Get chat_id from download record
        download = self.db.get_download(download_id)
        chat_id = download.get('chat_id') if download else None

        if not chat_id:
            raise ValueError("chat_id required for Playwright crawler")

        # Import crawler components
        from src.crawler.browser_manager import BrowserManager
        from src.crawler.playwright_crawler import PlaywrightCrawler

        try:
            from config import MAX_VIDEO_QUALITY
        except ImportError:
            MAX_VIDEO_QUALITY = '1080p'

        # Initialize browser manager and crawler
        browser_mgr = BrowserManager(headless=True)
        crawler = PlaywrightCrawler(browser_manager=browser_mgr, max_quality=MAX_VIDEO_QUALITY)

        # Find video URL
        try:
            video_info = await crawler.find_video_url(url, chat_id)

            if not video_info or 'url' not in video_info:
                raise Exception("Crawler failed to find video URL")

            download_url = video_info['url']
            title = video_info.get('title', video_info.get('filename', 'video'))
            ext = video_info.get('ext', 'mp4')

            # Sanitize title
            clean_title = self.sanitize_title(title)

            logger.info(f"Playwright extraction complete: {clean_title}.{ext}")

            return {
                'download_url': download_url,
                'headers': {},
                'cookies': [],
                'title': clean_title,
                'file_size': video_info.get('filesize')
            }

        finally:
            # Cleanup browser
            await browser_mgr.cleanup_all()
