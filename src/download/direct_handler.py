"""
Direct Download Handler - Smart Downloader

Phase 5: Direct Download Handler (yt-dlp)
Smart URL routing with quality-based file size filtering.
"""

import asyncio
import logging
import os
import re
from typing import Dict, Optional, Literal

from config import MAX_VIDEO_QUALITY, YTDLP_FORMAT, QUALITY_SIZE_LIMITS

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Base exception for download errors."""
    pass


class URLDetector:
    """
    URL Detector - Fast URL classification without full extraction.
    """

    def __init__(self):
        """Initialize URL detector."""
        self._yt_dlp_extractors = None

    def detect_url_type(self, url: str) -> Literal['ytdlp', 'direct', 'unknown']:
        """Detect URL type quickly."""
        if url.startswith('magnet:?'):
            return 'direct'  # Will be handled by torrent manager

        if not url.startswith(('http://', 'https://')):
            return 'unknown'

        # Direct file check
        if self._is_direct_file(url):
            return 'direct'

        # yt-dlp check (fast)
        if self._is_ytdlp_supported(url):
            return 'ytdlp'

        return 'direct'  # Fallback to HTTP download

    def _is_direct_file(self, url: str) -> bool:
        """Check if URL is direct file."""
        direct_ext = {
            '.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv',
            '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.wav',
            '.zip', '.rar', '.7z', '.tar', '.gz',
            '.pdf', '.doc', '.docx', '.exe', '.dmg'
        }
        return any(url.lower().endswith(ext) for ext in direct_ext)

    def _is_ytdlp_supported(self, url: str) -> bool:
        """Fast yt-dlp support check."""
        try:
            import yt_dlp
        except ImportError:
            return False

        if self._yt_dlp_extractors is None:
            ydl = yt_dlp.YoutubeDL({'quiet': True})
            self._yt_dlp_extractors = ydl._ies
            logger.debug(f"Loaded {len(self._yt_dlp_extractors)} yt-dlp extractors")

        for ie in self._yt_dlp_extractors:
            try:
                if ie.suitable(url):
                    logger.debug(f"yt-dlp extractor: {ie.IE_NAME}")
                    return True
            except Exception:
                continue

        return False


class DirectHandler:
    """
    Direct Handler - yt-dlp with Quality Filtering

    Handles yt-dlp downloads with quality-based size limits.
    Supports YouTube, Vimeo, and 1000+ sites.
    """

    # Telegram 2GB limit
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024

    def __init__(self, db, download_dir: str = '/tmp/downloads', max_quality: str = None):
        """
        Initialize direct handler.

        Args:
            db: Database instance
            download_dir: Download directory
            max_quality: Max quality ('1080p', '720p', '480p')
        """
        self.db = db
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

        self.max_quality = max_quality or MAX_VIDEO_QUALITY
        self.max_size = QUALITY_SIZE_LIMITS.get(self.max_quality, self.MAX_FILE_SIZE)

        self.url_detector = URLDetector()

        logger.info(f"DirectHandler initialized: max_quality={self.max_quality}, max_size={self.max_size//(1024**3)}GB")

    def get_ytdlp_format(self) -> str:
        """
        Get yt-dlp format string based on quality setting.

        Returns:
            Format string for yt-dlp
        """
        # Use specific format IDs for YouTube to ensure quality limit
        # For other sites, fall back to general format strings
        if self.max_quality == '1080p':
            # Best quality up to 1080p (default)
            return 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best'
        elif self.max_quality == '720p':
            # Max 720p - prefer 720p mp4 formats
            return 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/bestvideo[height<=720]/best'
        elif self.max_quality == '480p':
            # Max 480p
            return 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/bestvideo[height<=480]/best'
        else:
            # Default format string
            return YTDLP_FORMAT

    async def get_metadata(self, url: str) -> Dict:
        """
        Extract metadata without downloading.

        Args:
            url: URL to fetch metadata from

        Returns:
            Dictionary with metadata
        """
        logger.info(f"Extracting metadata for: {url}")

        try:
            import yt_dlp

            # Get format string for this quality
            format_str = self.get_ytdlp_format()

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': format_str,
            }

            # Force format selection for lower quality settings
            # This ensures yt-dlp picks the right resolution during metadata extraction
            if self.max_quality == '720p':
                # Prefer 720p or lower
                ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
                ydl_opts['format_sort'] = ['res:720']  # Prefer 720p
            elif self.max_quality == '480p':
                # Prefer 480p or lower
                ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]'
                ydl_opts['format_sort'] = ['res:480']  # Prefer 480p

            # Run in thread to avoid blocking
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, self._extract_info, url, ydl_opts)

            # Get file size from selected format
            filesize = None
            if 'requested_formats' in info:
                # Merged video+audio
                filesize = sum(f.get('filesize', 0) for f in info['requested_formats'] if f.get('filesize'))
            elif 'filesize' in info:
                filesize = info['filesize']

            # Extract video resolution
            height = info.get('height')
            width = info.get('width')
            resolution = f"{width}x{height}" if width and height else "unknown"

            metadata = {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration'),
                'filesize': filesize,
                'uploader': info.get('uploader'),
                'thumbnail': info.get('thumbnail'),
                'description': info.get('description'),
                'url': url,
                'resolution': resolution,
                'height': height,
                'width': width,
                'format': info.get('format'),
                'quality_setting': self.max_quality
            }

            if filesize:
                logger.info(f"Metadata: {resolution}, {filesize/(1024**2):.0f}MB")
            else:
                logger.info(f"Metadata: {resolution}, unknown size")
            return metadata

        except ImportError:
            raise DownloadError("yt-dlp not installed. Install with: pip install yt-dlp")
        except Exception as e:
            logger.error(f"Metadata extraction error: {e}")
            raise

    def _extract_info(self, url: str, ydl_opts: dict) -> dict:
        """Synchronous wrapper for yt-dlp extract_info."""
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def validate_file_size(self, metadata: Dict) -> bool:
        """
        Check if file is under size limit.

        Args:
            metadata: Metadata dictionary

        Returns:
            True if file size is valid
        """
        file_size = metadata.get('filesize')

        if file_size is None:
            logger.warning("Could not determine file size, proceeding anyway")
            return True

        if file_size > self.max_size:
            logger.warning(f"File too large: {file_size/(1024**3):.2f}GB > {self.max_size/(1024**3):.0f}GB")
            return False

        return True

    def validate_resolution(self, metadata: Dict) -> bool:
        """
        Check if video resolution is within quality limit.

        Args:
            metadata: Metadata dictionary

        Returns:
            True if resolution is valid
        """
        height = metadata.get('height')

        # If no height info, allow it (some sites don't provide it)
        if height is None:
            logger.debug("No height info in metadata, proceeding anyway")
            return True

        # Extract max height from quality setting
        max_h = int(self.max_quality.replace('p', ''))

        if height > max_h:
            logger.warning(f"Video {height}p exceeds max {self.max_quality} setting")
            return False

        logger.info(f"Resolution check passed: {height}p <= {max_h}p")
        return True

    async def download(self, url: str, download_id: int) -> str:
        """
        Download file with progress tracking.

        Args:
            url: URL to download
            download_id: Database download ID

        Returns:
            Path to downloaded file
        """
        # Get metadata first
        metadata = await self.get_metadata(url)

        # Validate resolution first (faster check)
        if not self.validate_resolution(metadata):
            height = metadata.get('height', 'unknown')
            raise ValueError(
                f"Video resolution {height}p exceeds max {self.max_quality}"
            )

        # Validate file size
        if not self.validate_file_size(metadata):
            file_size_gb = metadata.get('filesize', 0) / (1024 ** 3)
            raise ValueError(
                f"File too large: {file_size_gb:.2f} GB "
                f"(max for {self.max_quality}: {self.max_size/(1024**3):.0f} GB)"
            )

        # Update status
        self.db.update_download_status(download_id, 'downloading')
        logger.info(f"Starting download: {metadata['title']}")

        # Output template
        safe_title = re.sub(r'[^\w\s-]', '', metadata['title']).strip()[:50]
        output_template = os.path.join(self.download_dir, f'{safe_title}.%(ext)s')

        # Progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)

                progress = int(downloaded / total * 100) if total > 0 else 0

                self.db.update_progress(
                    download_id,
                    progress=progress,
                    download_speed=speed / (1024 * 1024) if speed else 0,
                    eta_seconds=eta
                )

        # yt-dlp configuration
        ydl_opts = {
            'outtmpl': output_template,
            'format': self.get_ytdlp_format(),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
        }

        try:
            import yt_dlp

            # Run download in thread
            loop = asyncio.get_event_loop()
            filename = await loop.run_in_executor(None, self._download, [url], ydl_opts)

            # Find downloaded file
            if not filename or not os.path.exists(filename):
                # Try to find it
                for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
                    test_path = os.path.join(self.download_dir, safe_title + ext)
                    if os.path.exists(test_path):
                        filename = test_path
                        break

            logger.info(f"Download complete: {filename}")

            # Mark complete
            self.db.update_progress(download_id, progress=100, download_speed=0, eta_seconds=0)

            return filename

        except ImportError:
            raise DownloadError("yt-dlp not installed")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise

    def _download(self, url: list, ydl_opts: dict) -> str:
        """Synchronous wrapper for yt-dlp download."""
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(url)
            # Return the prepared filename (approximation)
            info = ydl.extract_info(url[0], download=False)
            return ydl.prepare_filename(info)


class DirectHTTPHandler:
    """
    Direct HTTP Handler - For direct file downloads
    Handles direct HTTP/HTTPS downloads (not yt-dlp supported).
    """

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

    def __init__(self, db, download_dir: str = '/tmp/downloads'):
        """Initialize direct HTTP handler."""
        self.db = db
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    async def get_file_info(self, url: str) -> Dict:
        """Get file info via HEAD request."""
        try:
            import aiohttp
            import ssl

            # SSL context for expired certs
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.head(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)) as response:
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
            raise DownloadError("aiohttp not installed")
        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            raise

    async def download(self, url: str, download_id: int) -> str:
        """Download file with progress tracking."""
        try:
            import aiohttp
            import ssl

            # Get file info
            info = await self.get_file_info(url)

            # Validate size
            if info['filesize'] and info['filesize'] > self.MAX_FILE_SIZE:
                size_gb = info['filesize'] / (1024 ** 3)
                raise ValueError(f"File too large: {size_gb:.2f} GB")

            # Update status
            self.db.update_download_status(download_id, 'downloading')
            logger.info(f"Starting HTTP download: {info['filename']}")

            output_path = os.path.join(self.download_dir, info['filename'])

            # SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=600)) as response:
                    total = int(response.headers.get('Content-Length', 0))
                    downloaded = 0
                    chunk_size = 1024 * 1024  # 1MB
                    last_update = 0

                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if total > 0:
                                progress = int(downloaded / total * 100)
                                current_time = asyncio.get_event_loop().time()
                                if current_time - last_update >= 5:
                                    self.db.update_progress(
                                        download_id,
                                        progress=progress,
                                        download_speed=len(chunk) / (1024 * 1024),
                                        eta_seconds=0
                                    )
                                    last_update = current_time

            logger.info(f"HTTP download complete: {output_path}")

            self.db.update_progress(download_id, progress=100, download_speed=0, eta_seconds=0)

            return output_path

        except ImportError:
            raise DownloadError("aiohttp not installed")
        except Exception as e:
            logger.error(f"HTTP download failed: {e}")
            raise
