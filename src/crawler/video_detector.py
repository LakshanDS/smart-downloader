"""
Video Detector - Smart Downloader

Phase 6: Playwright Crawler - Video URL Detection
Identifies real videos from potential candidates (ads, previews, etc.).
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class VideoDetector:
    """
    Video Detector - Ad and Preview Filtering

    Filter candidates to find the real video from multiple video URLs.
    Filters out ads, previews, and promotional content.
    """

    # Quality size thresholds (bytes) - matching Telegram 2GB limit
    MAX_1080P_SIZE = 2 * 1024 * 1024 * 1024   # 2 GB - Telegram max, skip above
    MAX_720P_SIZE = 1 * 1024 * 1024 * 1024    # 1 GB - if targeting 720p max
    TARGET_1080P_SIZE = 800_000_000  # 800 MB - ideal 1080p target

    def __init__(self, max_quality: str = '1080p'):
        """
        Initialize video detector.

        Args:
            max_quality: Maximum quality to accept ('1080p', '720p', '480p')
        """
        self.ad_keywords = ['ad', 'advertisement', 'promo', 'preview', 'teaser',
                           'preroll', 'midroll', 'overlay', 'splash',
                           'commercial', 'sponsor', 'banner']
        self.min_duration = 30  # Seconds - minimum to not be an ad
        self.min_size = 1024 * 500  # 500 KB minimum

        # Set max file size based on quality preference
        self.max_quality = max_quality
        if max_quality == '1080p':
            self.max_size = self.MAX_1080P_SIZE
        elif max_quality == '720p':
            self.max_size = self.MAX_720P_SIZE
        elif max_quality == '480p':
            self.max_size = 500_000_000  # 500 MB
        else:
            self.max_size = self.MAX_1080P_SIZE

        logger.info(f"VideoDetector initialized with max_quality={max_quality}, max_size={self.max_size//(1024**3)}GB")

    def filter_videos(self, candidates: List[Dict]) -> Optional[Dict]:
        """
        Filter candidates to find the real video.

        Args:
            candidates: List of video candidate dictionaries

        Returns:
            Best matching video, or None if no valid videos
        """
        if not candidates:
            return None

        valid_videos = []

        for candidate in candidates:
            # Check content type
            if not self._is_video(candidate):
                logger.debug(f"Skipping non-video: {candidate.get('url', '')[:50]}")
                continue

            # Check if it's likely an ad
            if self._is_likely_ad(candidate):
                logger.info(f"Filtered out likely ad: {candidate['url'][:60]}")
                continue

            # Check file size (skip files larger than max quality)
            if self._is_too_large(candidate):
                logger.info(f"Filtered out: file too large for {self.max_quality} ({candidate.get('size', 0)/(1024**2):.0f}MB)")
                continue

            valid_videos.append(candidate)

        if not valid_videos:
            logger.warning(f"No valid videos after filtering {len(candidates)} candidates")
            return None

        # Return largest/longest (usually the real video)
        best_video = sorted(
            valid_videos,
            key=lambda x: (x.get('duration', 0), x.get('size', 0)),
            reverse=True
        )[0]

        size_mb = best_video.get('size', 0) / (1024 * 1024)
        logger.info(f"Selected best video: {size_mb:.0f}MB - {best_video['url'][:60]}")
        return best_video

    def _is_video(self, candidate: Dict) -> bool:
        """
        Check if URL appears to be a video.

        Args:
            candidate: Video candidate dictionary

        Returns:
            True if candidate is a video
        """
        content_type = candidate.get('content-type', candidate.get('content_type', ''))

        video_types = [
            'video/mp4', 'video/webm', 'video/ogg', 'video/x-matroska',
            'video/x-flv', 'video/x-msvideo', 'video/quicktime',
            'video/x-m4v', 'video/x-mpeg', 'video/3gpp', 'video/3gpp2'
        ]

        return any(vt in content_type.lower() for vt in video_types)

    def _is_likely_ad(self, candidate: Dict) -> bool:
        """
        Check for ad indicators.

        Args:
            candidate: Video candidate dictionary

        Returns:
            True if candidate is likely an ad
        """
        url = candidate.get('url', '').lower()

        # Check URL for ad keywords
        if any(keyword in url for keyword in self.ad_keywords):
            logger.debug(f"Ad keyword found in URL: {url[:60]}")
            return True

        # Check for suspiciously small files
        size = candidate.get('size', 0)
        if size > 0 and size < self.min_size:
            logger.debug(f"File too small: {size} bytes")
            return True

        # Duration check (if available)
        duration = candidate.get('duration', 0)
        if duration > 0 and duration < self.min_duration:
            logger.debug(f"Duration too short: {duration}s")
            return True

        return False

    def _is_too_large(self, candidate: Dict) -> bool:
        """
        Check if file is larger than max quality setting.

        Args:
            candidate: Video candidate dictionary

        Returns:
            True if file exceeds max quality size threshold
        """
        size = candidate.get('size', 0)

        # Only check if we have size info
        if size <= 0:
            return False

        # Check against max size threshold
        if size > self.max_size:
            size_mb = size / (1024 * 1024)
            logger.info(f"File {size_mb:.0f}MB exceeds max {self.max_quality} size ({self.max_size//(1024**3)}GB)")
            return True

        return False
