"""
Download Pooler - Smart Downloader

Non-blocking pooler process for downloads/uploads.
Polls database for pending jobs and processes them independently.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Optional, Dict
from telegram import Bot

logger = logging.getLogger(__name__)


class DownloadPooler:
    """
    Download Pooler - Separate Process Pooler

    Non-blocking download/upload system that:
    - Polls database for pending downloads
    - Routes to appropriate handler (torrent/direct/crawler)
    - Uploads completed files to Telegram
    - Handles retries with exponential backoff
    - Supports graceful shutdown

    Status flow: pending -> downloading -> downloaded -> uploading -> uploaded
    """

    def __init__(self, db, bot_token: str, db_path: str = None,
                 userbot_api_id: str = None, userbot_api_hash: str = None,
                 userbot_phone: str = None, download_dir: str = '/tmp/downloads',
                 aria2c_rpc_url: str = 'http://localhost:6800/jsonrpc'):
        """
        Initialize download pooler.

        Args:
            db: Database manager instance
            bot_token: Telegram bot token
            db_path: Path to SQLite database
            userbot_api_id: Userbot API ID (optional)
            userbot_api_hash: Userbot API hash (optional)
            userbot_phone: Userbot phone (optional)
            download_dir: Download directory
            aria2c_rpc_url: aria2c RPC URL for torrents
        """
        self.db = db
        self.db_path = db_path
        self.bot_token = bot_token
        self.download_dir = download_dir
        self.aria2c_rpc_url = aria2c_rpc_url

        # State tracking
        self.running = True
        self.current_download_id: Optional[int] = None
        self.current_upload_id: Optional[int] = None
        self.shutdown_event = asyncio.Event()

        # Initialize bot
        try:
            self.bot = Bot(token=bot_token)
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            self.bot = None

        # Initialize handlers
        from .upload_handler import UploadHandler
        from .retry_handler import RetryHandler

        self.upload_handler = UploadHandler(
            db=db,
            bot_token=bot_token,
            bot_instance=self.bot,
            userbot_api_id=userbot_api_id,
            userbot_api_hash=userbot_api_hash,
            userbot_phone=userbot_phone
        )

        self.retry_handler = RetryHandler(db=db)

        # Download handlers (lazy init)
        self.direct_downloader = None
        self.torrent_manager = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info("DownloadPooler initialized")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals for graceful cleanup."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
        self.shutdown_event.set()

    def _init_download_handlers(self):
        """Initialize download handlers lazily."""
        if not self.direct_downloader:
            from src.download.direct_downloader import DirectDownloader
            self.direct_downloader = DirectDownloader(
                db=self.db,
                download_dir=self.download_dir,
                rpc_url=self.aria2c_rpc_url
            )
            logger.info("DirectDownloader initialized")

        if not self.torrent_manager:
            from src.download.torrent_manager import TorrentManager
            self.torrent_manager = TorrentManager(
                db=self.db,
                rpc_url=self.aria2c_rpc_url
            )
            logger.info("TorrentManager initialized")

    async def start(self, poll_interval: int = 1):
        """
        Main pooler loop.

        Args:
            poll_interval: Database poll interval in seconds
        """
        logger.info("DownloadPooler started")

        # Initialize download handlers
        self._init_download_handlers()

        while self.running:
            try:
                # Check for shutdown signal
                if self.shutdown_event.is_set():
                    logger.info("Shutdown event received, stopping pooler...")
                    break

                # Process downloads (one at a time)
                if self.current_download_id is None:
                    download = await self._get_next_pending_download()
                    if download:
                        # Create task for download (non-blocking)
                        asyncio.create_task(self._process_download(download))
                    else:
                        # No downloads, check uploads
                        if self.current_upload_id is None:
                            upload = await self._get_next_completed_upload()
                            if upload:
                                # Create task for upload (non-blocking)
                                asyncio.create_task(self._process_upload(upload))

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                logger.info("Pooler cancelled")
                break
            except Exception as e:
                logger.error(f"Pooler loop error: {e}", exc_info=True)
                await asyncio.sleep(5)

        # Graceful shutdown
        await self._shutdown()

    async def _get_next_pending_download(self) -> Optional[Dict]:
        """Get next pending download from database."""
        # Check if DB has the method, if not add it
        if hasattr(self.db, 'get_next_pending_download'):
            return self.db.get_next_pending_download()
        else:
            # Fallback to existing method
            return self.db.get_next_pending()

    async def _get_next_completed_upload(self) -> Optional[Dict]:
        """Get next completed download ready for upload."""
        if hasattr(self.db, 'get_next_completed_upload'):
            return self.db.get_next_completed_upload()
        else:
            # Query for 'downloaded' status files without file_id
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM downloads
                    WHERE status = 'downloaded'
                      AND file_id IS NULL
                    ORDER BY added_date ASC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                return dict(row) if row else None

    async def _process_download(self, download: Dict):
        """
        Process a single download.

        Args:
            download: Download record from database
        """
        download_id = download['id']
        url = download['url']
        source = download.get('source', 'direct')

        self.current_download_id = download_id
        logger.info(f"Processing download {download_id}: {source}")

        try:
            # Update status to downloading
            self.db.update_download_status(download_id, 'downloading')

            # Route to appropriate handler
            if source == 'torrent':
                file_path = await self._download_torrent(download_id, url)
            elif source == 'direct':
                file_path = await self._download_direct(download_id, url)
            elif source == 'ytdlp':
                file_path = await self._download_ytdlp(download_id, url)
            elif source == 'crawler':
                file_path = await self._download_crawler(download_id, url)
            elif source == 'playwright':
                file_path = await self._download_crawler(download_id, url)
            else:
                raise ValueError(f"Unknown source: {source}")

            # Download complete - update status and file path
            self.db.update_download_status(download_id, 'downloaded')
            self.db.update_progress(download_id, progress=100, download_speed=0, eta_seconds=0)

            # Save file path to database for upload
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE downloads
                    SET file_path = ?, updated_at = ?
                    WHERE id = ?
                """, (file_path, datetime.now().isoformat(), download_id))
                conn.commit()

            logger.info(f"Download complete: {download_id} -> {file_path}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed for {download_id}: {error_msg}")

            # Handle retry
            will_retry = await self.retry_handler.handle_failure(download_id, error_msg)

            if not will_retry:
                # Notify user of permanent failure
                await self._notify_download_failed(download, error_msg)

        finally:
            self.current_download_id = None

    async def _download_torrent(self, download_id: int, magnet: str) -> str:
        """Download torrent via aria2c."""
        if not self.torrent_manager:
            raise Exception("TorrentManager not initialized")

        # Check aria2c connection
        if not self.torrent_manager.check_connection():
            raise Exception("aria2c RPC not connected")

        # Add magnet to aria2c
        gid = self.torrent_manager.download_magnet(magnet)
        logger.info(f"Torrent added: {gid}")

        # Monitor download progress
        import time
        last_update = 0

        while True:
            status = self.torrent_manager.get_status(gid)

            # Update progress in DB
            if status['status'] in ['active', 'waiting']:
                progress = int(status.get('progress', 0) * 100)
                speed = status.get('download_speed', 0) / (1024 * 1024)  # MB/s
                eta = status.get('eta', 0)

                current_time = time.time()
                if current_time - last_update >= 5:  # Update every 5s
                    self.db.update_progress(download_id, progress, speed, eta_seconds=eta)
                    last_update = current_time

                await asyncio.sleep(2)

            elif status['status'] == 'complete':
                logger.info(f"Torrent complete: {gid}")
                return status.get('file_path', '/tmp/downloaded_file')

            elif status['status'] == 'error':
                raise Exception(f"Torrent download failed: {status.get('error', 'Unknown error')}")

            elif status['status'] == 'removed':
                raise Exception("Torrent was removed")

            await asyncio.sleep(1)

    async def _download_direct(self, download_id: int, url: str) -> str:
        """Download direct URL via DirectDownloader (aria2c)."""
        if not self.direct_downloader:
            raise Exception("DirectDownloader not initialized")

        return await self.direct_downloader.download_from_ytdlp(url, download_id)

    async def _download_ytdlp(self, download_id: int, url: str) -> str:
        """Download yt-dlp URL via DirectDownloader (aria2c)."""
        if not self.direct_downloader:
            raise Exception("DirectDownloader not initialized")

        return await self.direct_downloader.download_from_ytdlp(url, download_id)

    async def _download_crawler(self, download_id: int, url: str) -> str:
        """Download via Playwright crawler using DirectDownloader (aria2c)."""
        if not self.direct_downloader:
            raise Exception("DirectDownloader not initialized")

        # Get chat_id from download record
        download = self.db.get_download(download_id)
        chat_id = download.get('chat_id') if download else None

        if not chat_id:
            raise ValueError("chat_id required for crawler")

        return await self.direct_downloader.download_from_crawler(url, chat_id, download_id)

    async def _process_upload(self, download: Dict):
        """
        Upload completed file to Telegram.

        Args:
            download: Download record with 'downloaded' status
        """
        download_id = download['id']
        file_path = download.get('file_path')

        self.current_upload_id = download_id
        logger.info(f"Processing upload {download_id}: {file_path}")

        try:
            # Upload to Telegram
            file_id = await self.upload_handler.upload(
                download_id=download_id,
                file_path=file_path,
                caption=f"Downloaded via Smart Downloader",
                chat_id=download.get('chat_id')
            )

            if file_id:
                logger.info(f"Upload complete: {download_id} -> {file_id}")
                await self._notify_upload_complete(download)
            else:
                logger.warning(f"Upload returned no file_id for {download_id}")

        except Exception as e:
            logger.error(f"Upload failed for {download_id}: {e}")
            # Status already reverted to 'downloaded' by upload_handler

        finally:
            self.current_upload_id = None

    async def _notify_download_failed(self, download: Dict, error: str):
        """Notify user of download failure."""
        if not self.bot:
            return

        chat_id = download.get('chat_id')
        if not chat_id:
            return

        message = f"""
❌ **Download Failed**

{download.get('title', 'Unknown')}

Error: {error}

Retries exhausted.
        """

        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send failure notification: {e}")

    async def _notify_upload_complete(self, download: Dict):
        """Notify user of upload completion."""
        if not self.bot:
            return

        chat_id = download.get('chat_id')
        if not chat_id:
            return

        message = f"""
✅ **Upload Complete**

{download.get('title', 'File')}

Check your saved messages!
        """

        try:
            await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send completion notification: {e}")

    async def _shutdown(self):
        """Graceful shutdown - wait for current operations."""
        logger.info("Initiating graceful shutdown...")

        # Wait for current download to complete (with timeout)
        if self.current_download_id:
            logger.info(f"Waiting for download {self.current_download_id} to complete...")
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=300  # 5 minute timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Download timeout, forcing shutdown")

        # Wait for current upload to complete (no timeout - uploads should finish)
        if self.current_upload_id:
            logger.info(f"Waiting for upload {self.current_upload_id} to complete...")
            while self.current_upload_id:
                await asyncio.sleep(1)

        # Disconnect handlers
        if self.upload_handler:
            await self.upload_handler.disconnect()

        logger.info("DownloadPooler shutdown complete")
