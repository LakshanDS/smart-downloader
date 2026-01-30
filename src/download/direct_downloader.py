"""
Direct Downloader - Smart Downloader

Unified downloader using aria2c for all non-torrent downloads.
Handles yt-dlp extracted URLs and Playwright crawler found URLs.
"""

import asyncio
import logging
import os
import re
import tempfile
from typing import Dict, Optional
from urllib.parse import urlparse

try:
    from ..config import ARIA2C_RPC_URL, DOWNLOAD_DIR, MAX_VIDEO_QUALITY
except ImportError:
    from config import ARIA2C_RPC_URL, DOWNLOAD_DIR, MAX_VIDEO_QUALITY

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Base exception for download errors."""
    pass


class DirectDownloader:
    """
    Direct Downloader - aria2c-based download handler

    Downloads files via aria2c RPC with multi-stream support.
    Sources:
    - yt-dlp extracted URLs (with headers/cookies)
    - Playwright crawler found URLs
    - Direct file URLs
    """

    def __init__(self, db, download_dir: str = None, rpc_url: str = None):
        """
        Initialize direct downloader.

        Args:
            db: Database manager instance
            download_dir: Download directory
            rpc_url: aria2c RPC URL
        """
        self.db = db
        # Ensure absolute path
        self.download_dir = os.path.abspath(download_dir or DOWNLOAD_DIR)
        self.rpc_url = rpc_url or ARIA2C_RPC_URL
        self.aria = None
        self.current_gid = None

        # Create download dir
        os.makedirs(self.download_dir, exist_ok=True)
        logger.info(f"DirectDownloader initialized with download_dir: {self.download_dir}")

        # Initialize aria2c
        self._init_aria2()

    def _init_aria2(self):
        """Initialize aria2p API."""
        try:
            import aria2p
            from urllib.parse import urlparse

            # Parse RPC URL to get host and port
            parsed = urlparse(self.rpc_url)
            host = parsed.hostname or 'localhost'
            port = parsed.port or 6800

            # Add http:// scheme if not present for aria2p
            if parsed.scheme:
                host = f"{parsed.scheme}://{host}"

            client = aria2p.Client(host=host, port=port)
            self.aria = aria2p.API(client)
            logger.info(f"DirectDownloader: aria2c connected to {self.rpc_url}")
        except ImportError:
            logger.error("aria2p not installed. Install with: pip install aria2p")
            raise DownloadError("aria2p not installed")
        except Exception as e:
            logger.error(f"Failed to connect to aria2c: {e}")
            raise DownloadError(f"aria2c connection failed: {e}")

    def sanitize_title(self, title: str, max_length: int = 32) -> str:
        """
        Clean title for use as filename.

        - Remove emojis and special characters
        - Keep only letters, numbers, spaces, hyphens, underscores
        - Trim to max_length characters

        Args:
            title: Raw title string
            max_length: Maximum filename length

        Returns:
            Sanitized filename (without extension)
        """
        if not title:
            return "download"

        # Remove emojis and non-ASCII
        cleaned = re.sub(r'[^\x00-\x7F]+', '', title)

        # Keep only alphanumeric, spaces, hyphens, underscores
        cleaned = re.sub(r'[^a-zA-Z0-9\s\-_]', '', cleaned)

        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Trim and limit length
        cleaned = cleaned.strip().title()

        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].strip()

        return cleaned or "download"

    async def download_from_ytdlp(self, url: str, download_id: int) -> str:
        """
        Extract download URL from yt-dlp and download via aria2c.

        Args:
            url: Video URL
            download_id: Database download ID

        Returns:
            Path to downloaded file
        """
        logger.info(f"Extracting info from yt-dlp: {url}")

        # Extract info using yt-dlp
        video_info, headers, cookies = await self._extract_ytdlp_info(url)

        if not video_info or 'url' not in video_info:
            raise DownloadError("Failed to extract download URL from yt-dlp")

        download_url = video_info['url']
        title = video_info.get('title', 'video')
        ext = video_info.get('ext', 'mp4')

        # Sanitize filename
        clean_title = self.sanitize_title(title)
        filename = f"{clean_title}.{ext}"

        logger.info(f"Downloading via aria2c: {filename}")

        # Download via aria2c with headers and cookies
        return await self._download_with_aria2(
            url=download_url,
            filename=filename,
            download_id=download_id,
            headers=headers,
            cookies=cookies
        )

    async def download_from_crawler(self, url: str, chat_id: int, download_id: int) -> str:
        """
        Find video URL using Playwright crawler and download via aria2c.

        Args:
            url: Page URL to crawl
            chat_id: User's chat ID (for browser context isolation)
            download_id: Database download ID

        Returns:
            Path to downloaded file
        """
        from src.crawler.browser_manager import BrowserManager
        from src.crawler.playwright_crawler import PlaywrightCrawler

        logger.info(f"Crawling page: {url}")

        # Initialize browser manager and crawler
        browser_mgr = BrowserManager(headless=True)
        crawler = PlaywrightCrawler(browser_manager=browser_mgr, max_quality=MAX_VIDEO_QUALITY)

        # Find video URL
        try:
            video_info = await crawler.find_video_url(url, chat_id)

            if not video_info or 'url' not in video_info:
                raise DownloadError("Crawler failed to find video URL")

            download_url = video_info['url']
            title = video_info.get('title', video_info.get('filename', 'video'))
            ext = video_info.get('ext', 'mp4')

        finally:
            # Cleanup browser
            await browser_mgr.cleanup_all()

        # Sanitize filename
        clean_title = self.sanitize_title(title)
        filename = f"{clean_title}.{ext}"

        logger.info(f"Downloading crawled video via aria2c: {filename}")

        # Download via aria2c
        return await self._download_with_aria2(
            url=download_url,
            filename=filename,
            download_id=download_id
        )

    async def _extract_ytdlp_info(self, url: str) -> tuple:
        """
        Extract direct URL, headers, and cookies using yt-dlp.

        Args:
            url: Video URL

        Returns:
            Tuple of (video_info, headers_dict, cookies_list)
        """
        try:
            import yt_dlp
        except ImportError:
            raise DownloadError("yt-dlp not installed")

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

                return format_info, headers, cookies

        return await loop.run_in_executor(None, _extract)

    async def _download_with_aria2(self, url: str, filename: str,
                                   download_id: int,
                                   headers: Dict = None,
                                   cookies = None) -> str:
        """
        Download file via aria2c RPC.

        Args:
            url: Direct download URL
            filename: Output filename
            download_id: Database download ID for progress tracking
            headers: HTTP headers dict
            cookies: Cookie list

        Returns:
            Path to downloaded file
        """
        output_path = os.path.join(self.download_dir, filename)

        # Build aria2c options
        options = {
            'dir': self.download_dir,
            'out': filename,
            'max-connection-per-server': 16,
            'split': 16,
            'split-every-mb': 10,
            'continue': 'true',
            'auto-file-renaming': 'true',
        }

        # Add headers
        if headers:
            header_list = [f"{k}: {v}" for k, v in headers.items()]
            if header_list:
                options['header'] = header_list

        # Add cookies
        if cookies:
            cookie_str = '; '.join([f"{c.name}={c.value}" for c in cookies])
            options['cookie'] = cookie_str

        # Add to aria2c
        try:
            # Set global dir option before download (aria2c bug: per-download dir doesn't always work)
            self.aria.set_global_options({'dir': self.download_dir})
            logger.debug(f"Set aria2c global dir to: {self.download_dir}")

            download_obj = self.aria.add_uris([url], options=options)
            gid = download_obj.gid
            self.current_gid = gid
            logger.info(f"Added to aria2c: {gid} - {filename}")
        except Exception as e:
            logger.error(f"Failed to add to aria2c: {e}")
            raise DownloadError(f"aria2c add failed: {e}")

        # Monitor download
        return await self._monitor_download(gid, download_id, output_path)

    async def _monitor_download(self, gid: str, download_id: int, output_path: str) -> str:
        """
        Monitor aria2c download progress and update database.

        Args:
            gid: aria2c GID
            download_id: Database download ID
            output_path: Expected output file path

        Returns:
            Path to downloaded file
        """
        logger.info(f"Monitoring download {gid}...")

        while True:
            try:
                download = self.aria.get_download(gid)
                status = download.status

                # Calculate progress
                total_length = download.total_length
                completed_length = download.completed_length

                if total_length > 0:
                    progress = int((completed_length / total_length) * 100)
                else:
                    progress = 0

                # Update database (convert timedelta eta to seconds)
                eta_seconds = int(download.eta.total_seconds()) if download.eta else 0
                self.db.update_progress(
                    download_id,
                    progress=progress,
                    download_speed=download.download_speed,
                    eta_seconds=eta_seconds
                )

                # Check if complete
                if status == 'complete':
                    logger.info(f"Download complete: {gid}")
                    # Get actual file path from aria2c
                    logger.debug(f"Aria2 download.dir: {download.dir}")
                    logger.debug(f"Self download_dir: {self.download_dir}")
                    logger.debug(f"Download files: {download.files}")
                    logger.debug(f"Root files paths: {download.root_files_paths}")

                    # aria2c returns relative paths, combine with our known absolute download_dir
                    found_path = None

                    # Method 1: Use root_files_paths if it's absolute
                    if download.root_files_paths and len(download.root_files_paths) > 0:
                        path = download.root_files_paths[0]
                        if path.is_absolute():
                            found_path = str(path)
                            logger.debug(f"Found absolute path from root_files_paths: {found_path}")

                    # Method 2: Construct from self.download_dir + filename
                    if not found_path and download.files and len(download.files) > 0:
                        filename = download.files[0].path
                        # filename might be relative or just the name
                        if os.path.isabs(filename):
                            found_path = filename
                        else:
                            # Get just the filename from the path
                            basename = os.path.basename(filename)
                            found_path = os.path.join(self.download_dir, basename)
                        logger.debug(f"Constructed path: {found_path}")

                    # Method 3: Try expected path
                    if not found_path or not os.path.exists(found_path):
                        found_path = output_path
                        logger.debug(f"Trying expected path: {found_path}")

                    # Verify and return
                    if found_path and os.path.exists(found_path):
                        logger.info(f"Downloaded file found: {found_path}")
                        self.db.update_download_status(download_id, 'downloaded')
                        return found_path
                    else:
                        raise DownloadError(f"Download complete but file not found. Tried: {found_path}")

                # Check if errored
                if status == 'error':
                    error_code = download.error_code
                    error_msg = download.error_message
                    logger.error(f"Download error {gid}: {error_code} - {error_msg}")
                    raise DownloadError(f"aria2c download failed: {error_msg}")

                # Check if removed
                if status == 'removed':
                    logger.warning(f"Download {gid} was removed")
                    raise DownloadError("Download was removed")

                # Wait before next check
                await asyncio.sleep(2)

            except Exception as e:
                if isinstance(e, DownloadError):
                    raise
                logger.error(f"Error monitoring download: {e}")
                await asyncio.sleep(2)
