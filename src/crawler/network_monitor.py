"""
Network Monitor - Smart Downloader

Phase 6: Playwright Crawler - Network Request Monitoring
Captures all video URLs from network requests during page load.
"""

import logging
from typing import List, Set, Callable, Dict

logger = logging.getLogger(__name__)


class NetworkMonitor:
    """
    Network Monitor - URL Capture

    Capture all video URLs from network requests.
    Used during page loading to find video URLs.
    """

    def __init__(self):
        """Initialize network monitor."""
        self.video_urls: Set[str] = set()
        self.candidates: List[Dict] = []

    def capture_urls(self) -> Callable:
        """
        Return a callback for Playwright response handler.

        Returns:
            Callback function that can be passed to page.on('response')
        """
        def on_response(response):
            content_type = response.headers.get('content-type', '')
            url = response.url

            # Only care about video responses
            if 'video' not in content_type.lower():
                return

            self.video_urls.add(url)

            self.candidates.append({
                'url': url,
                'content-type': content_type,
                'status': response.status,
                'headers': dict(response.headers),
                'size': int(response.headers.get('content-length', 0)) if response.headers.get('content-length') else 0
            })

            logger.debug(f"Captured video URL: {url[:80]}")

        return on_response

    def get_candidates(self) -> List[Dict]:
        """
        Return all captured video URLs.

        Returns:
            List of candidate video dictionaries
        """
        return self.candidates.copy()

    def get_unique_urls(self) -> List[str]:
        """
        Return list of unique video URLs.

        Returns:
            List of unique video URLs
        """
        return list(self.video_urls)

    def reset(self):
        """Clear captured URLs."""
        self.video_urls.clear()
        self.candidates.clear()
        logger.debug("Network monitor reset")
