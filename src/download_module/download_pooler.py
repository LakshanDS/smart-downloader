"""
Download Pooler - Download Module

Non-blocking pooler for downloads only.
Polls database for pending downloads and processes them with 3-stage pipeline.

Upload is handled separately by upload_module.UploadPooler.
"""

import asyncio
import logging
import signal
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class DownloadPooler:
    """
    Download Pooler - Separate Process for Downloads

    Non-blocking download system that:
    - Polls database for pending downloads
    - Uses 3-stage pipeline: URL Detection → URL Extraction → aria2c Download
    - Handles retries with exponential backoff
    - Supports graceful shutdown
    - Supports cancel (no pause/resume)

    Status flow: pending → downloading → downloaded
    """

    def __init__(self, db, download_dir: str = './downloads',
                 aria2c_rpc_url: str = 'http://localhost:6800/jsonrpc',
                 aria2c_rpc_secret: str = ''):
        """
        Initialize download pooler.

        Args:
            db: Database manager instance
            download_dir: Download directory
            aria2c_rpc_url: aria2c RPC URL for downloads
            aria2c_rpc_secret: aria2c RPC secret (optional, for authentication)
        """
        self.db = db
        self.download_dir = download_dir
        self.aria2c_rpc_url = aria2c_rpc_url
        self.aria2c_rpc_secret = aria2c_rpc_secret

        # State tracking
        self.running = True
        self.current_download_id: Optional[int] = None
        self.shutdown_event = asyncio.Event()

        # Initialize components
        from .url_detector import get_url_detector
        from .aria2c_downloader import Aria2cDownloader
        from .retry_handler import RetryHandler

        self.url_detector = get_url_detector()
        self.aria2c_downloader = Aria2cDownloader(
            db=db,
            rpc_url=aria2c_rpc_url,
            download_dir=download_dir,
            rpc_secret=aria2c_rpc_secret
        )
        self.retry_handler = RetryHandler(db=db)

        # Extractors (lazy init)
        self.extractors = {}

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info("DownloadPooler initialized")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals for graceful cleanup."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
        self.shutdown_event.set()

    async def start(self, poll_interval: int = 1):
        """
        Main pooler loop.

        Args:
            poll_interval: Database poll interval in seconds
        """
        logger.info("DownloadPooler started")

        # Handle interrupted downloads on startup
        await self._handle_interrupted_downloads()

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

    async def _handle_interrupted_downloads(self):
        """Handle downloads that were interrupted (status='downloading')."""
        interrupted = self.db.get_all_downloads(status='downloading')
        for download in interrupted:
            download_id = download['id']
            logger.info(f"Found interrupted download: {download_id}")

            # Reset to pending for restart
            self.db.update_download_status(download_id, 'pending')
            logger.info(f"Reset interrupted download {download_id} to pending")

    async def _process_download(self, download: Dict):
        """
        Process a single download with 3-stage pipeline.

        Args:
            download: Download record from database
        """
        download_id = download['id']
        url = download['url']

        self.current_download_id = download_id
        logger.info(f"Processing download {download_id}: {url[:50]}...")

        try:
            # Update status to downloading
            self.db.update_download_status(download_id, 'downloading')

            # Stage 1: URL Detection
            detection = self.url_detector.detect(url)
            url_type = detection['type']
            logger.info(f"Stage 1 - URL type: {url_type}")

            # Stage 2: URL Extraction
            extractor = self._get_extractor(url_type)
            extracted = await extractor.extract(url, download_id)

            # Update metadata in database
            self.db.update_download_metadata(
                download_id,
                title=extracted['title'],
                file_size=extracted['file_size']
            )

            logger.info(f"Stage 2 - URL extraction complete: {extracted['title']}")

            # Stage 3: Download via aria2c
            filename = f"{extracted['title']}.{self._get_extension(url_type)}"
            file_path = await self.aria2c_downloader.download(
                url=extracted['download_url'],
                filename=filename,
                download_id=download_id,
                headers=extracted.get('headers'),
                cookies=extracted.get('cookies')
            )

            # Download complete - update status and file path
            self.db.update_download_status(download_id, 'downloaded')
            self.db.update_file_path(download_id, file_path)

            logger.info(f"Download complete: {download_id} -> {file_path}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed for {download_id}: {error_msg}")

            # Handle retry
            will_retry = await self.retry_handler.handle_failure(download_id, error_msg)

            if not will_retry:
                # Mark as failed
                self.db.update_download_status(download_id, 'failed', error_msg)

        finally:
            self.current_download_id = None

    def _get_extractor(self, url_type: str):
        """Get appropriate extractor for URL type."""
        from .extractors import (
            TorrentExtractor,
            YtdlpExtractor,
            PlaywrightExtractor,
            DirectExtractor
        )

        # Lazy load extractors
        if url_type not in self.extractors:
            if url_type == 'torrent':
                self.extractors['torrent'] = TorrentExtractor(self.db)
            elif url_type == 'ytdlp':
                self.extractors['ytdlp'] = YtdlpExtractor(self.db)
            elif url_type == 'playwright':
                self.extractors['playwright'] = PlaywrightExtractor(self.db)
            elif url_type == 'direct':
                self.extractors['direct'] = DirectExtractor(self.db)
            else:
                logger.warning(f"Unknown URL type: {url_type}")
                self.extractors[url_type] = DirectExtractor(self.db)

        return self.extractors.get(url_type)

    def _get_extension(self, url_type: str) -> str:
        """Get file extension based on URL type."""
        extensions = {
            'torrent': 'torrent',
            'ytdlp': 'mp4',
            'playwright': 'mp4',
            'direct': 'mp4'
        }
        return extensions.get(url_type, 'mp4')

    async def _shutdown(self):
        """Graceful shutdown - wait for current download to complete."""
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

        logger.info("DownloadPooler shutdown complete")


# === Main Entry Point (for subprocess execution) ===

if __name__ == "__main__":
    """Main entry point when run as subprocess."""
    import sys
    import logging
    from pathlib import Path

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Add project root to path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # Import config
    import src.config
    from database.manager import DatabaseManager

    # Initialize database
    db = DatabaseManager(src.config.DATABASE_PATH)

    # Create and start pooler
    pooler = DownloadPooler(
        db=db,
        download_dir=src.config.DOWNLOAD_DIR,
        aria2c_rpc_url=src.config.ARIA2C_RPC_URL,
        aria2c_rpc_secret=src.config.ARIA2C_RPC_SECRET
    )

    # Run pooler (this blocks until shutdown)
    try:
        asyncio.run(pooler.start(poll_interval=src.config.POOLER_POLL_INTERVAL))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Pooler error: {e}", exc_info=True)
    finally:
        db.close()
        logger.info("Pooler exited")
