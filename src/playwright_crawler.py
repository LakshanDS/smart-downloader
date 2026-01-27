"""
Playwright Crawler - Smart Downloader

Phase 6: Playwright Crawler - Main Crawler
Headless browser automation to download from unsupported sites.
"""

import asyncio
import hashlib
import logging
from typing import Optional, Dict

from browser_manager import BrowserManager
from network_monitor import NetworkMonitor
from video_detector import VideoDetector

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Base exception for download errors."""
    pass


class PlaywrightCrawler:
    """
    Playwright Crawler - Unsupported Site Downloader

    Headless browser crawler for unsupported sites.
    Finds real video URLs from pages that don't support yt-dlp.
    """

    def __init__(self, browser_manager: BrowserManager):
        """Initialize crawler."""
        self.browser = browser_manager
        self.detector = VideoDetector()
        self.monitor = NetworkMonitor()

    async def find_video_url(self, url: str, chat_id: int) -> Optional[Dict]:
        """
        Find the real video URL from a page.

        Args:
            url: URL to crawl
            chat_id: User's chat ID for context isolation

        Returns:
            Dictionary with video info, or None if not found
        """
        context = self.browser.get_context(chat_id)
        page = context.new_page()

        try:
            # Set up network monitoring
            monitor_callback = self.monitor.capture_urls()
            page.on('response', monitor_callback)

            # Navigate to page
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)

            # Wait for video player to load
            await self._wait_for_video_player(page)

            # Wait a bit more for network requests
            await asyncio.sleep(3)

            # Get all captured URLs
            candidates = self.monitor.get_candidates()

            if not candidates:
                logger.warning(f"No video URLs captured from {url}")
                return None

            logger.info(f"Found {len(candidates)} video URL candidates")

            # Filter to find real video
            real_video = self.detector.filter_videos(candidates)

            if real_video:
                logger.info(f"Selected real video: {real_video['url']}")

                # Add metadata if we can get it
                real_video['source_url'] = url
                real_video['method'] = 'playwright'

                return real_video
            else:
                logger.warning(f"No valid video found from candidates")
                return None

        except Exception as e:
            logger.error(f"Crawler error for {url}: {e}", exc_info=True)
            raise DownloadError(f"Failed to crawl page: {str(e)}")

        finally:
            self.monitor.reset()
            self.browser.cleanup_context(chat_id)

    async def _wait_for_video_player(self, page) -> None:
        """
        Wait for video player to appear.

        Args:
            page: Playwright page object
        """
        selectors = [
            'video',
            '.video-player',
            '.player',
            '.video-container',
            '[role="main"]',
            'iframe[src*="video"]',
            '[id*="player"]',
            'object[type*="video"]',
            'embed[type*="video"]'
        ]

        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=5000)
                if element:
                    logger.debug(f"Found video player with selector: {selector}")
                    return
            except:
                continue

        # Wait a bit for dynamic content
        await asyncio.sleep(2)

    async def probe_video(self, url: str) -> Dict:
        """
        Download small sample to detect metadata.

        Args:
            url: Video URL to probe

        Returns:
            Dictionary with metadata
        """
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                # Use HEAD request first
                async with session.head(url, allow_redirects=True) as response:
                    headers = dict(response.headers)

                    return {
                        'url': url,
                        'content-type': headers.get('content-type', ''),
                        'content-length': headers.get('content-length'),
                        'status': response.status
                    }

        except ImportError:
            logger.error("aiohttp not installed")
            return {'url': url, 'error': 'aiohttp not installed'}
        except Exception as e:
            logger.error(f"Failed to probe video: {e}")
            return {'url': url, 'error': str(e)}
