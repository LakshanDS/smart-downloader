"""
Direct Download Handler - Smart Downloader

Phase 5: Direct Download Handler (yt-dlp)
Handles direct HTTP/HTTPS downloads and yt-dlp supported sites with metadata-first file size validation.
"""

import asyncio
import logging
import json
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Base exception for download errors."""
    pass


class DirectHandler:
    """
    Direct Handler - yt-dlp Integration

    Handle direct downloads via yt-dlp.
    Supports YouTube, Vimeo, and 1000+ sites.
    """

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

    def __init__(self, db, download_dir: str = '/tmp/downloads'):
        """Initialize direct handler."""
        self.db = db
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    async def get_metadata(self, url: str) -> Dict:
        """
        Extract metadata without downloading.

        Args:
            url: URL to fetch metadata from

        Returns:
            Dictionary with metadata (title, duration, filesize, etc.)
        """
        logger.info(f"Extracting metadata for: {url}")

        try:
            # Use yt-dlp to get metadata
            cmd = [
                'yt-dlp',
                '--skip-download',
                '--dump-json',
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"Metadata extraction failed: {error_msg}")
                raise ValueError(f"Could not extract metadata: {error_msg[:100]}")

            # Parse JSON output
            metadata = json.loads(stdout.decode())

            return {
                'title': metadata.get('title', 'Unknown'),
                'duration': metadata.get('duration'),
                'filesize': metadata.get('filesize'),
                'uploader': metadata.get('uploader'),
                'thumbnail': metadata.get('thumbnail'),
                'description': metadata.get('description'),
                'url': url
            }

        except Exception as e:
            logger.error(f"Metadata extraction error: {e}")
            raise

    def validate_file_size(self, metadata: Dict) -> bool:
        """
        Check if file is under 2GB limit.

        Args:
            metadata: Metadata dictionary

        Returns:
            True if file size is valid
        """
        file_size = metadata.get('filesize')

        if file_size is None:
            # Could not determine size, allow it but warn
            logger.warning("Could not determine file size, proceeding anyway")
            return True

        if file_size > self.MAX_FILE_SIZE:
            logger.warning(f"File too large: {file_size} bytes")
            return False

        return True

    async def download(self, url: str, download_id: int) -> str:
        """
        Download file with progress tracking.

        Args:
            url: URL to download
            download_id: Database download ID for progress updates

        Returns:
            Path to downloaded file
        """
        # First, get metadata
        metadata = await self.get_metadata(url)

        # Validate file size
        if not self.validate_file_size(metadata):
            file_size_gb = metadata.get('filesize', 0) / (1024 ** 3)
            raise ValueError(
                f"File too large: {file_size_gb:.2f} GB "
                f"(Telegram limit: 2 GB)"
            )

        # Update download info in DB
        self.db.update_download_status(
            download_id,
            'downloading'
        )

        logger.info(f"Starting download: {metadata['title']}")

        # Download template
        output_template = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        # Progress callback
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)

                if total > 0:
                    progress = int(downloaded / total * 100)
                else:
                    progress = 0

                # Update database
                self.db.update_progress(
                    download_id,
                    progress=progress,
                    download_speed=speed / (1024 * 1024) if speed else 0,  # MB/s
                    eta_seconds=eta
                )

        # yt-dlp configuration
        ydl_opts = {
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'nocookies': True,
            'nocheckcertificate': True,
        }

        # Download using yt-dlp Python API
        try:
            import yt_dlp

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find downloaded file
            filename = ydl.prepare_filename(metadata)

            if not os.path.exists(filename):
                # Try alternative extensions
                base = os.path.splitext(filename)[0]
                for ext in ['.mp4', '.webm', '.mkv', '.mp3']:
                    alt_path = base + ext
                    if os.path.exists(alt_path):
                        filename = alt_path
                        break

            logger.info(f"Download complete: {filename}")

            # Mark as complete
            self.db.update_progress(
                download_id,
                progress=100,
                download_speed=0,
                eta_seconds=0
            )

            return filename

        except ImportError:
            logger.error("yt-dlp not installed")
            raise DownloadError("yt-dlp not installed. Install with: pip install yt-dlp")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise


class DirectHTTPHandler:
    """
    Direct HTTP Handler - For direct HTTP/HTTPS links
    Handles direct HTTP/HTTPS downloads that aren't yt-dlp supported.
    """

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

    def __init__(self, db, download_dir: str = '/tmp/downloads'):
        """Initialize direct HTTP handler."""
        self.db = db
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    async def get_file_info(self, url: str) -> Dict:
        """
        Get file info via HEAD request.

        Args:
            url: URL to check

        Returns:
            Dictionary with file info
        """
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True) as response:
                    content_length = response.headers.get('Content-Length')
                    content_type = response.headers.get('Content-Type', '')

                    # Try to get filename from URL
                    filename = url.split('/')[-1]
                    if '.' not in filename:
                        filename = 'download'

                    return {
                        'filesize': int(content_length) if content_length else None,
                        'filename': filename,
                        'content_type': content_type,
                        'url': url
                    }
        except ImportError:
            logger.error("aiohttp not installed")
            raise DownloadError("aiohttp not installed. Install with: pip install aiohttp")
        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            raise

    async def download(self, url: str, download_id: int) -> str:
        """
        Download file with progress tracking.

        Args:
            url: URL to download
            download_id: Database download ID for progress updates

        Returns:
            Path to downloaded file
        """
        try:
            import aiohttp

            # Get file info first
            info = await self.get_file_info(url)

            # Validate size
            if info['filesize'] and info['filesize'] > self.MAX_FILE_SIZE:
                size_gb = info['filesize'] / (1024 ** 3)
                raise ValueError(f"File too large: {size_gb:.2f} GB")

            # Update download info in DB
            self.db.update_download_status(
                download_id,
                'downloading'
            )

            logger.info(f"Starting HTTP download: {info['filename']}")

            # Start download
            output_path = os.path.join(self.download_dir, info['filename'])

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    total = int(response.headers.get('Content-Length', 0))
                    downloaded = 0
                    chunk_size = 1024 * 1024  # 1MB chunks
                    last_update = 0

                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Update progress every 5%
                            if total > 0:
                                progress = int(downloaded / total * 100)

                                # Update database periodically (not every chunk)
                                current_time = asyncio.get_event_loop().time()
                                if current_time - last_update >= 5:  # 5 second intervals
                                    self.db.update_progress(
                                        download_id,
                                        progress=progress,
                                        download_speed=len(chunk) / (1024 * 1024),  # Rough estimate
                                        eta_seconds=0
                                    )
                                    last_update = current_time

            logger.info(f"HTTP download complete: {output_path}")

            # Mark as complete
            self.db.update_progress(
                download_id,
                progress=100,
                download_speed=0,
                eta_seconds=0
            )

            return output_path

        except ImportError:
            logger.error("aiohttp not installed")
            raise DownloadError("aiohttp not installed. Install with: pip install aiohttp")
        except Exception as e:
            logger.error(f"HTTP download failed: {e}")
            raise
