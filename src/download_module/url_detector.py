"""
URL Detector - Download Module (Stage 1)

Smart URL routing to detect the best download method.
Fast URL classification to avoid wasted time on unsupported methods.
"""

import logging
import re
from typing import Dict, Literal
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

    # yt-dlp supported sites list URL
    YTDLP_SITES_URL = 'https://raw.githubusercontent.com/yt-dlp/yt-dlp/refs/heads/master/supportedsites.md'

    def __init__(self):
        """Initialize URL detector."""
        self._yt_dlp_domains = None

    def detect(self, url: str) -> Dict:
        """
        Detect URL type and return classification.

        Args:
            url: URL to classify

        Returns:
            Dictionary with:
                'type': 'torrent' | 'direct' | 'ytdlp' | 'playwright' | 'unknown'
                'url': str
        """
        # Check for magnet links first
        if url.startswith('magnet:?'):
            logger.debug("URL type: torrent (magnet link)")
            return {'type': 'torrent', 'url': url}

        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URL format: {url[:50]}")
            return {'type': 'unknown', 'url': url}

        # Check for direct file URLs
        if self._is_direct_file_url(url):
            logger.debug("URL type: direct (file extension)")
            return {'type': 'direct', 'url': url}

        # Check if yt-dlp supports this (using official sites list)
        if self._is_ytdlp_supported(url):
            logger.debug("URL type: yt-dlp supported")
            return {'type': 'ytdlp', 'url': url}

        # Default to playwright for unsupported sites
        logger.debug("URL type: playwright (unsupported video site)")
        return {'type': 'playwright', 'url': url}

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
        Check if yt-dlp supports this URL using official sites list.

        Downloads and caches the yt-dlp supported sites list from GitHub.
        Checks if the URL's domain is in the supported sites list.

        Args:
            url: URL to check

        Returns:
            True if yt-dlp supports this URL, False otherwise
        """
        # Lazy load and cache yt-dlp patterns
        if self._yt_dlp_domains is None:
            self._yt_dlp_domains = self._load_ytdlp_domains()

        # Check if URL matches any yt-dlp pattern
        url_lower = url.lower()

        for pattern in self._yt_dlp_domains:
            # Pattern matching logic:
            # - *youtube* -> URL contains "youtube"
            # - *youtu.be* -> URL contains "youtu.be"
            # - exact.com -> URL contains "exact.com"
            try:
                # Remove wildcards and check if pattern is in URL
                clean_pattern = pattern.replace('*', '')
                if clean_pattern in url_lower:
                    logger.debug(f"yt-dlp supported (pattern: {pattern})")
                    return True
            except Exception:
                continue

        return False

    def _load_ytdlp_domains(self) -> set:
        """
        Load yt-dlp supported patterns from GitHub.

        Downloads the supportedsites.md file and extracts URL patterns.

        Returns:
            Set of URL patterns (lowercase)
        """
        import requests

        logger.info("Loading yt-dlp supported sites list from GitHub...")

        try:
            # Download the supported sites list
            response = requests.get(self.YTDLP_SITES_URL, timeout=10)
            response.raise_for_status()

            # Parse the markdown file to extract URL patterns
            patterns = set()
            lines = response.text.split('\n')

            # Parse lines like:
            # - **youtube**: [*youtube*](## "netrc machine") YouTube
            # - **youtube:clip**: [*youtube*](## "netrc machine") YouTube Shorts
            for line in lines:
                # Match lines with extractor pattern
                match = re.match(r'^\s*-\s*\*\*([^:]+):\s*\[\*([^\]]+)\]', line)
                if match:
                    extractor_name = match.group(1).lower()
                    url_pattern = match.group(2).lower()
                    patterns.add(url_pattern)
                    logger.debug(f"yt-dlp extractor: {extractor_name} -> pattern: {url_pattern}")

            logger.info(f"Loaded {len(patterns)} yt-dlp supported patterns")
            return patterns

        except requests.RequestException as e:
            logger.error(f"Failed to download yt-dlp sites list: {e}")
            # Fallback to empty set - will use playwright for all sites
            return set()
        except Exception as e:
            logger.error(f"Error parsing yt-dlp sites list: {e}")
            return set()


# Singleton instance
_detector = None


def get_url_detector() -> URLDetector:
    """Get singleton URL detector instance."""
    global _detector
    if _detector is None:
        _detector = URLDetector()
    return _detector
