"""
Extractors Package - URL Extraction (Stage 2)

Contains extractors for different URL types:
- TorrentExtractor: Magnet/torrent links
- YtdlpExtractor: yt-dlp supported sites
- PlaywrightExtractor: Playwright crawler
- DirectExtractor: Direct file URLs
"""

from .base_extractor import BaseExtractor
from .torrent_extractor import TorrentExtractor
from .ytdlp_extractor import YtdlpExtractor
from .playwright_extractor import PlaywrightExtractor
from .direct_extractor import DirectExtractor

__all__ = [
    'BaseExtractor',
    'TorrentExtractor',
    'YtdlpExtractor',
    'PlaywrightExtractor',
    'DirectExtractor'
]
