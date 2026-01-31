"""
aria2c Downloader - Download Module (Stage 3)

Download file using aria2c RPC with progress tracking and cancel support.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class Aria2cDownloader:
    """Stage 3: Download via aria2c RPC with cancel support"""

    def __init__(self, db, rpc_url: str, download_dir: str, rpc_secret: str = ''):
        """
        Initialize aria2c downloader.

        Args:
            db: Database manager instance
            rpc_url: aria2c RPC URL
            download_dir: Download directory
            rpc_secret: aria2c RPC secret (optional, for authentication)
        """
        self.db = db
        # Ensure absolute path
        self.download_dir = os.path.abspath(download_dir)
        self.rpc_url = rpc_url
        self.rpc_secret = rpc_secret
        self.aria = None
        self.current_gid: Optional[str] = None

        # Create download dir
        os.makedirs(self.download_dir, exist_ok=True)
        logger.info(f"Aria2cDownloader initialized with download_dir: {self.download_dir}")

        # Initialize aria2c
        self._init_aria2c()

    def _init_aria2c(self):
        """Initialize aria2p API."""
        try:
            import aria2p
        except ImportError:
            logger.error("aria2p not installed. Install with: pip install aria2p")
            raise ImportError("aria2p not installed")
        except Exception as e:
            logger.error(f"Failed to connect to aria2c: {e}")
            raise Exception(f"aria2c connection failed: {e}")

        # Parse RPC URL to get host and port
        parsed = urlparse(self.rpc_url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 6800

        # Add http:// scheme if not present for aria2p
        if parsed.scheme:
            host = f"{parsed.scheme}://{host}"

        client = aria2p.Client(host=host, port=port, secret=self.rpc_secret)
        self.aria = aria2p.API(client)
        logger.info(f"Aria2cDownloader: aria2c connected to {self.rpc_url}")

    async def download(self, url: str, filename: str, download_id: int,
                    headers: Dict = None, cookies: List = None) -> str:
        """
        Download file via aria2c.

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
            raise Exception(f"aria2c add failed: {e}")

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

                # Check cancel status
                if await self._is_cancelled(download_id):
                    await self._stop_download(gid)
                    self.db.update_download_status(download_id, 'cancelled')
                    raise Exception("Download cancelled by user")

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
                        raise Exception(f"Download complete but file not found. Tried: {found_path}")

                # Check if errored
                if status == 'error':
                    error_code = download.error_code
                    error_msg = download.error_message
                    logger.error(f"Download error {gid}: {error_code} - {error_msg}")
                    raise Exception(f"aria2c download failed: {error_msg}")

                # Check if removed
                if status == 'removed':
                    logger.warning(f"Download {gid} was removed")
                    raise Exception("Download was removed")

                # Wait before next check
                await asyncio.sleep(2)

            except Exception as e:
                if isinstance(e, Exception) and "cancelled by user" in str(e):
                    raise
                logger.error(f"Error monitoring download: {e}")
                await asyncio.sleep(2)

    def get_progress(self, gid: str) -> dict:
        """
        Get download progress (for testing).

        Args:
            gid: aria2c GID

        Returns:
            Dictionary with progress info or None if not found
        """
        try:
            download = self.aria.get_download(gid)
            return {
                'gid': gid,
                'status': download.status,
                'progress': (download.completed_length / download.total_length * 100) if download.total_length > 0 else 0,
                'downloadSpeed': download.download_speed,
                'uploadSpeed': download.upload_speed,
                'eta': int(download.eta.total_seconds()) if download.eta else 0,
                'totalLength': download.total_length,
                'completedLength': download.completed_length
            }
        except Exception as e:
            logger.error(f"Failed to get progress for {gid}: {e}")
            return None

    async def _stop_download(self, gid: str):
        """Stop aria2c download."""
        try:
            self.aria.remove([gid], force=True)
            logger.info(f"Stopped aria2c download: {gid}")
        except Exception as e:
            logger.error(f"Failed to stop download {gid}: {e}")

    async def _is_cancelled(self, download_id: int) -> bool:
        """Check if download is cancelled in database."""
        download = self.db.get_download(download_id)
        return download.get('cancelled', False) if download else False
