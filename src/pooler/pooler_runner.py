"""
Pooler Runner - Smart Downloader

Entry point for the pooler subprocess.
Runs as a separate process for non-blocking downloads/uploads.
"""

import asyncio
import logging
import multiprocessing
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from config import DATABASE_PATH
from database.manager import DatabaseManager
from .download_pooler import DownloadPooler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pooler.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Global pooler instance (for signal handling)
_pooler_instance = None


def run_pooler_process(db_path: str, bot_token: str, userbot_api_id: str = None,
                       userbot_api_hash: str = None, userbot_phone: str = None,
                       download_dir: str = '/tmp/downloads',
                       aria2c_rpc_url: str = 'http://localhost:6800/jsonrpc',
                       poll_interval: int = 1):
    """
    Run pooler as a separate process.

    Args:
        db_path: Path to SQLite database
        bot_token: Telegram bot token
        userbot_api_id: Userbot API ID (optional)
        userbot_api_hash: Userbot API hash (optional)
        userbot_phone: Userbot phone (optional)
        download_dir: Download directory
        aria2c_rpc_url: aria2c RPC URL
        poll_interval: Database poll interval in seconds
    """
    global _pooler_instance

    logger.info("Starting pooler process...")
    logger.info(f"Database: {db_path}")
    logger.info(f"Download dir: {download_dir}")

    # Create download directory if not exists
    os.makedirs(download_dir, exist_ok=True)

    # Initialize database
    db = DatabaseManager(db_path)

    # Initialize pooler
    _pooler_instance = DownloadPooler(
        db=db,
        bot_token=bot_token,
        db_path=db_path,
        userbot_api_id=userbot_api_id,
        userbot_api_hash=userbot_api_hash,
        userbot_phone=userbot_phone,
        download_dir=download_dir,
        aria2c_rpc_url=aria2c_rpc_url
    )

    # Run pooler
    try:
        asyncio.run(_pooler_instance.start(poll_interval=poll_interval))
    except KeyboardInterrupt:
        logger.info("Pooler process interrupted")
    except Exception as e:
        logger.error(f"Pooler process error: {e}", exc_info=True)
    finally:
        logger.info("Pooler process stopped")


class PoolerProcess:
    """
    Pooler Process Manager

    Manages the pooler subprocess lifecycle from the main bot process.
    """

    def __init__(self, db_path: str, bot_token: str, userbot_api_id: str = None,
                 userbot_api_hash: str = None, userbot_phone: str = None,
                 download_dir: str = '/tmp/downloads',
                 aria2c_rpc_url: str = 'http://localhost:6800/jsonrpc',
                 poll_interval: int = 1):
        """
        Initialize pooler process manager.

        Args:
            db_path: Path to SQLite database
            bot_token: Telegram bot token
            userbot_api_id: Userbot API ID (optional)
            userbot_api_hash: Userbot API hash (optional)
            userbot_phone: Userbot phone (optional)
            download_dir: Download directory
            aria2c_rpc_url: aria2c RPC URL
            poll_interval: Database poll interval in seconds
        """
        self.db_path = db_path
        self.bot_token = bot_token
        self.userbot_api_id = userbot_api_id
        self.userbot_api_hash = userbot_api_hash
        self.userbot_phone = userbot_phone
        self.download_dir = download_dir
        self.aria2c_rpc_url = aria2c_rpc_url
        self.poll_interval = poll_interval

        self.process: multiprocessing.Process = None
        self.running = False

    def start(self) -> bool:
        """
        Start pooler subprocess.

        Returns:
            True if started successfully
        """
        if self.running:
            logger.warning("Pooler process already running")
            return False

        self.process = multiprocessing.Process(
            target=run_pooler_process,
            kwargs={
                'db_path': self.db_path,
                'bot_token': self.bot_token,
                'userbot_api_id': self.userbot_api_id,
                'userbot_api_hash': self.userbot_api_hash,
                'userbot_phone': self.userbot_phone,
                'download_dir': self.download_dir,
                'aria2c_rpc_url': self.aria2c_rpc_url,
                'poll_interval': self.poll_interval
            },
            daemon=False
        )

        self.process.start()
        self.running = True

        logger.info(f"Pooler process started (PID: {self.process.pid})")
        return True

    def stop(self, timeout: int = 30) -> bool:
        """
        Stop pooler subprocess.

        Args:
            timeout: Timeout in seconds

        Returns:
            True if stopped successfully
        """
        if not self.running:
            logger.warning("Pooler process not running")
            return False

        logger.info("Stopping pooler process...")

        # Send SIGTERM for graceful shutdown
        self.process.terminate()

        # Wait for process to exit
        self.process.join(timeout=timeout)

        # Force kill if still running
        if self.process.is_alive():
            logger.warning("Pooler process did not stop gracefully, killing...")
            self.process.kill()
            self.process.join(timeout=5)

        self.running = False
        logger.info("Pooler process stopped")
        return True

    def is_alive(self) -> bool:
        """Check if pooler process is alive."""
        return self.process and self.process.is_alive()

    def get_pid(self) -> int:
        """Get pooler process PID."""
        return self.process.pid if self.process else None


# Global pooler process instance
_pooler_process: PoolerProcess = None


def start_pooler_process(db_path: str = None,
                         bot_token: str = None,
                         userbot_api_id: str = None,
                         userbot_api_hash: str = None,
                         userbot_phone: str = None,
                         download_dir: str = '/tmp/downloads',
                         aria2c_rpc_url: str = 'http://localhost:6800/jsonrpc',
                         poll_interval: int = 1) -> PoolerProcess:
    """
    Start pooler process (singleton).

    Args:
        db_path: Path to SQLite database
        bot_token: Telegram bot token
        userbot_api_id: Userbot API ID (optional)
        userbot_api_hash: Userbot API hash (optional)
        userbot_phone: Userbot phone (optional)
        download_dir: Download directory
        aria2c_rpc_url: aria2c RPC URL
        poll_interval: Database poll interval in seconds

    Returns:
        PoolerProcess instance
    """
    global _pooler_process

    if _pooler_process and _pooler_process.is_alive():
        logger.warning("Pooler process already running")
        return _pooler_process

    # Load from environment if not provided
    if not bot_token:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not userbot_api_id:
        userbot_api_id = os.getenv('USERBOT_API_ID')

    if not userbot_api_hash:
        userbot_api_hash = os.getenv('USERBOT_API_HASH')

    if not userbot_phone:
        userbot_phone = os.getenv('USERBOT_PHONE')

    if not db_path:
        db_path = DATABASE_PATH

    if not download_dir:
        download_dir = os.getenv('DOWNLOAD_DIR', '/tmp/downloads')

    _pooler_process = PoolerProcess(
        db_path=db_path,
        bot_token=bot_token,
        userbot_api_id=userbot_api_id,
        userbot_api_hash=userbot_api_hash,
        userbot_phone=userbot_phone,
        download_dir=download_dir,
        aria2c_rpc_url=aria2c_rpc_url,
        poll_interval=poll_interval
    )

    _pooler_process.start()
    return _pooler_process


def stop_pooler_process(timeout: int = 30) -> bool:
    """
    Stop pooler process (singleton).

    Args:
        timeout: Timeout in seconds

    Returns:
        True if stopped successfully
    """
    global _pooler_process

    if not _pooler_process:
        logger.warning("No pooler process to stop")
        return False

    result = _pooler_process.stop(timeout=timeout)
    _pooler_process = None
    return result


def get_pooler_status() -> dict:
    """
    Get pooler process status.

    Returns:
        Dictionary with status info
    """
    global _pooler_process

    if not _pooler_process:
        return {
            'running': False,
            'pid': None
        }

    return {
        'running': _pooler_process.is_alive(),
        'pid': _pooler_process.get_pid()
    }


if __name__ == '__main__':
    # Run pooler directly (for testing)
    import os
    from dotenv import load_dotenv

    load_dotenv()

    run_pooler_process(
        db_path=DATABASE_PATH,
        bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
        userbot_api_id=os.getenv('USERBOT_API_ID'),
        userbot_api_hash=os.getenv('USERBOT_API_HASH'),
        userbot_phone=os.getenv('USERBOT_PHONE'),
        download_dir=os.getenv('DOWNLOAD_DIR', '/tmp/downloads'),
        aria2c_rpc_url=os.getenv('ARIA2C_RPC_URL', 'http://localhost:6800/jsonrpc'),
        poll_interval=int(os.getenv('POOLER_POLL_INTERVAL', '1'))
    )
