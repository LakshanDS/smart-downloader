"""
Test Configuration - Smart Downloader

Minimal config for testing. Override src.config during tests.
"""

# Bot configuration - mock token for tests
BOT_TOKEN = 'test_token_12345'
DATABASE_PATH = ':memory:'  # In-memory DB for tests

# Download settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
PROGRESS_UPDATE_INTERVAL = 1  # Faster for tests
RETRY_DELAYS = [0, 0, 0]  # No retries in tests

# aria2c / Torrent settings
ARIA2C_RPC_URL = 'http://localhost:6800/jsonrpc'
ARIA2C_RPC_SECRET = ''
ARIA2C_DOWNLOAD_DIR = '/tmp/test/torrents'
ARIA2C_MAX_CONCURRENT = 1

# Direct download settings
DOWNLOAD_DIR = '/tmp/test/downloads'
YTDLP_FORMAT = 'best'

# Playwright / Crawler settings
BROWSER_HEADLESS = True
BROWSER_TIMEOUT = 10000  # 10 seconds for tests

# Userbot credentials - mocked
UPLOADER_API_ID = '123'
UPLOADER_API_HASH = 'test_hash'
UPLOADER_PHONE = '+1234567890'

# Logging
LOG_LEVEL = 'DEBUG'
