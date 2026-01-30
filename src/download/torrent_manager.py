"""
Torrent Manager - Smart Downloader

Phase 4: Torrent Handler (aria2c)
Integrates aria2c RPC for magnet/torrent downloads with real-time progress tracking.
"""

import logging
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Base exception for download errors."""
    pass


class InvalidURLError(Exception):
    """Raised when URL is invalid."""
    pass


class TorrentManager:
    """
    Torrent Manager - aria2c Integration

    Manage aria2c RPC for torrent downloads.
    """

    def __init__(self, db, rpc_url: str = "http://localhost:6800/jsonrpc"):
        """Initialize torrent manager."""
        self.db = db
        self.rpc_url = rpc_url
        self.aria = None

        # Try to import aria2p
        try:
            import aria2p
            self.aria = aria2p.API(rpc_url)
        except ImportError:
            logger.error("aria2p not installed. Install with: pip install aria2p")
            self.aria = None

    def check_connection(self) -> bool:
        """Verify aria2c RPC is running."""
        if not self.aria:
            return False

        try:
            version = self.aria.get_stats()
            logger.info(f"aria2c connected: version available")
            return True
        except Exception as e:
            logger.error(f"aria2c connection failed: {e}")
            return False

    def download_magnet(self, magnet: str, chat_id: int = None,
                        message_id: int = None, user_id: int = None) -> Optional[str]:
        """
        Add magnet link to download queue.

        Args:
            magnet: Magnet link string
            chat_id: User's chat ID for progress updates
            message_id: Telegram message ID
            user_id: Telegram user ID

        Returns:
            GID of the download, or None if failed
        """
        if not self.aria:
            raise DownloadError("aria2c not available. Install aria2p and start aria2c RPC.")

        try:
            # Validate magnet link
            if not magnet.startswith("magnet:?"):
                raise InvalidURLError("Invalid magnet link format")

            # Parse magnet for basic info
            info = self._parse_magnet(magnet)
            title = info.get('name', 'Unknown torrent')

            logger.info(f"Adding torrent: {title}")

            # Add to aria2c
            gid = self.aria.add_magnet(
                magnet,
                options={
                    'max-connection-per-server': 16,
                    'split': 16,
                    'split-every-mb': 10,
                    'continue': 'true',
                }
            )

            logger.info(f"Added torrent {gid}: {title}")

            # Store in database
            if self.db:
                try:
                    self.db.add_to_queue(
                        url=magnet,
                        source='torrent',
                        title=title,
                        chat_id=chat_id,
                        message_id=message_id
                    )

                    # Log activity
                    self.db.log_activity(
                        user_id=user_id,
                        chat_id=chat_id,
                        action='torrent_queued',
                        metadata={'gid': gid, 'magnet': magnet[:50]}
                    )
                except Exception as e:
                    logger.error(f"Failed to add to database: {e}")

            return gid

        except InvalidURLError as e:
            raise e
        except Exception as e:
            logger.error(f"Failed to add magnet: {e}", exc_info=True)
            raise DownloadError(f"Could not add torrent: {str(e)}")

    def _parse_magnet(self, magnet: str) -> Dict:
        """
        Parse basic info from magnet link.

        Args:
            magnet: Magnet link string

        Returns:
            Dictionary with 'name', 'xt', 'trackers', 'size'
        """
        try:
            import urllib.parse

            parsed = urllib.parse.urlparse(magnet)
            params = urllib.parse.parse_qs(parsed.query)

            xt = params.get('xt', [''])[0]
            name = params.get('dn', ['Unknown'])[0]
            tr = params.get('tr', [])

            return {
                'name': name,
                'xt': xt,
                'trackers': tr,
                'size': 0  # Unknown from magnet alone
            }
        except Exception:
            return {
                'name': 'Unknown torrent',
                'xt': '',
                'trackers': [],
                'size': 0
            }

    def get_status(self, gid: str) -> Dict:
        """
        Get download status for a specific GID.

        Args:
            gid: aria2c GID (Global ID)

        Returns:
            Dictionary with status information
        """
        if not self.aria:
            return {
                'status': 'error',
                'progress': 0,
                'downloaded': 0,
                'total_size': 0,
                'download_speed': 0,
                'eta': 0,
                'gid': gid
            }

        try:
            status = self.aria.tell_status(gid)

            return {
                'status': status.state,
                'progress': status.progress,
                'downloaded': status.completed_length,
                'total_size': status.total_length,
                'download_speed': status.download_speed,
                'eta': status.eta,
                'gid': gid
            }
        except Exception as e:
            logger.error(f"Failed to get status for {gid}: {e}")
            return {
                'status': 'error',
                'progress': 0,
                'downloaded': 0,
                'total_size': 0,
                'download_speed': 0,
                'eta': 0,
                'gid': gid
            }

    def pause_download(self, gid: str) -> bool:
        """
        Pause a download.

        Args:
            gid: aria2c GID

        Returns:
            True if paused successfully
        """
        if not self.aria:
            return False

        try:
            self.aria.pause([gid])
            logger.info(f"Paused download {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause {gid}: {e}")
            return False

    def remove_download(self, gid: str, force: bool = False) -> bool:
        """
        Remove download from queue.

        Args:
            gid: aria2c GID
            force: Force removal even if active

        Returns:
            True if removed successfully
        """
        if not self.aria:
            return False

        try:
            self.aria.remove([gid], force=force)
            logger.info(f"Removed download {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove {gid}: {e}")
            return False

    def get_active_downloads(self) -> list:
        """
        Get list of all active downloads from aria2c.

        Returns:
            List of download objects
        """
        if not self.aria:
            return []

        try:
            return self.aria.tell_active()
        except Exception as e:
            logger.error(f"Failed to get active downloads: {e}")
            return []

    def get_waiting_downloads(self) -> list:
        """
        Get list of waiting downloads from aria2c.

        Returns:
            List of download objects
        """
        if not self.aria:
            return []

        try:
            return self.aria.tell_waiting()
        except Exception as e:
            logger.error(f"Failed to get waiting downloads: {e}")
            return []

    def get_global_stats(self) -> Dict:
        """
        Get global aria2c statistics.

        Returns:
            Dictionary with global stats
        """
        if not self.aria:
            return {}

        try:
            stats = self.aria.get_global_stat()
            return {
                'download_speed': stats.download_speed,
                'upload_speed': stats.upload_speed,
                'num_active': stats.num_active,
                'num_waiting': stats.num_waiting,
                'num_stopped': stats.num_stopped,
                'num_stopped_total': stats.num_stopped_total
            }
        except Exception as e:
            logger.error(f"Failed to get global stats: {e}")
            return {}
