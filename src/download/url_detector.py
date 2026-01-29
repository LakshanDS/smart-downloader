"""
URL Detector - Smart Downloader

Smart URL routing to detect the best download method.
Fast URL classification to avoid wasted time on unsupported methods.
"""

import logging
from typing import Literal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class URLDetector:
    """
    URL Detector - Smart Download Method Routing

    Quickly classifies URLs to determine the best download method:
    - Direct file URLs → HTTP download
    - yt-dlp supported sites → yt-dlp
    - Unsupported video sites → Playwright crawler
    - Magnet links → Torrent handler
    """

    # Direct file extensions
    DIRECT_EXTENSIONS = {
        # Video
        '.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv',
        '.m4v', '.mpg', '.mpeg', '.3gp', '.ogv',
        # Audio
        '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.opus', '.wav',
        # Archives
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
        # Documents
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
        # Other
        '.exe', '.dmg', '.iso', '.apk'
    }

    def __init__(self):
        """Initialize URL detector."""
        self._yt_dlp_extractors = None

    def detect_url_type(self, url: str) -> Literal['direct', 'ytdlp', 'playwright', 'torrent', 'unknown']:
        """
        Detect the best download method for a URL.

        Args:
            url: URL to classify

        Returns:
            Method type: 'direct', 'ytdlp', 'playwright', 'torrent', 'unknown'
        """
        # Check for magnet links first
        if url.startswith('magnet:?'):
            logger.debug("URL type: torrent (magnet link)")
            return 'torrent'

        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URL format: {url[:50]}")
            return 'unknown'

        # Check for direct file URLs
        if self._is_direct_file_url(url):
            logger.debug("URL type: direct (file extension)")
            return 'direct'

        # Check if yt-dlp supports this (fast check)
        if self._is_ytdlp_supported(url):
            logger.debug("URL type: yt-dlp supported")
            return 'ytdlp'

        # Default to playwright for unsupported sites
        logger.debug("URL type: playwright (unsupported video site)")
        return 'playwright'

    def _is_direct_file_url(self, url: str) -> bool:
        """
        Check if URL points to a direct file download.

        Args:
            url: URL to check

        Returns:
            True if URL appears to be a direct file
        """
        url_lower = url.lower()

        # Check file extension
        for ext in self.DIRECT_EXTENSIONS:
            if url_lower.endswith(ext):
                return True

        # Check for download indicators in URL path
        path = urlparse(url).path.lower()
        download_indicators = ['/download/', '/files/', '/getfile/', '/get_file/']
        if any(indicator in path for indicator in download_indicators):
            return True

        return False

    def _is_ytdlp_supported(self, url: str) -> bool:
        """
        Fast check if yt-dlp supports this URL.

        Uses yt-dlp's ie.suitable() method without full extraction.

        Args:
            url: URL to check

        Returns:
            True if yt-dlp has an extractor for this URL
        """
        try:
            import yt_dlp
        except ImportError:
            logger.warning("yt-dlp not installed")
            return False

        # Lazy load extractors
        if self._yt_dlp_extractors is None:
            ydl = yt_dlp.YoutubeDL({'quiet': True})
            self._yt_dlp_extractors = ydl._ies
            logger.debug(f"Loaded {len(self._yt_dlp_extractors)} yt-dlp extractors")

        # Fast check - iterate extractors and call suitable()
        for ie in self._yt_dlp_extractors:
            try:
                if ie.suitable(url):
                    # Extractor found!
                    logger.debug(f"yt-dlp extractor: {ie.IE_NAME}")
                    return True
            except Exception:
                # Some extractors raise errors during suitable() check
                continue

        return False

    def get_max_quality_size(self, quality: str = '1080p') -> int:
        """
        Get max file size for quality setting.

        Args:
            quality: Quality level ('1080p', '720p', '480p')

        Returns:
            Max size in bytes
        """
        from config import QUALITY_SIZE_LIMITS
        return QUALITY_SIZE_LIMITS.get(quality, QUALITY_SIZE_LIMITS['1080p'])


# Singleton instance
_detector = None

def get_url_detector() -> URLDetector:
    """Get singleton URL detector instance."""
    global _detector
    if _detector is None:
        _detector = URLDetector()
    return _detector
