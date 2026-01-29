"""
Configuration - Smart Downloader

Loads environment variables and app configuration.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

OWNER_ID = os.getenv('OWNER_ID')
if not OWNER_ID:
    raise ValueError("OWNER_ID environment variable is required (get from @userinfobot)")

DATABASE_PATH = os.getenv('DATABASE_PATH', 'smart_downloader.db')

# Download settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes
PROGRESS_UPDATE_INTERVAL = 5  # seconds
RETRY_DELAYS = [0, 120, 480]  # 0s, 2min, 8min (exponential backoff)

# aria2c / Torrent settings
ARIA2C_RPC_URL = os.getenv('ARIA2C_RPC_URL', 'http://localhost:6800/jsonrpc')
ARIA2C_RPC_SECRET = os.getenv('ARIA2C_RPC_SECRET', '')  # Optional
ARIA2C_DOWNLOAD_DIR = os.getenv('ARIA2C_DOWNLOAD_DIR', '/downloads/torrents')
ARIA2C_MAX_CONCURRENT = int(os.getenv('ARIA2C_MAX_CONCURRENT', '3'))

# Direct download settings
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/tmp/downloads')
YTDLP_FORMAT = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

# Video quality settings for Playwright crawler
# Options: '1080p', '720p', '480p' - files larger than these thresholds will be skipped
MAX_VIDEO_QUALITY = os.getenv('MAX_VIDEO_QUALITY', '1080p')

# Quality size thresholds (bytes)
QUALITY_SIZE_LIMITS = {
    '1080p': 2 * 1024 * 1024 * 1024,  # 2 GB (Telegram limit)
    '720p': 900_000_000,     # 900 MB
    '480p': 500_000_000,     # 500 MB
}

# Playwright / Crawler settings
BROWSER_HEADLESS = os.getenv('BROWSER_HEADLESS', 'true').lower() == 'true'
BROWSER_TIMEOUT = int(os.getenv('BROWSER_TIMEOUT', '30000'))  # 30 seconds

# Userbot credentials (for Phase 7 - Userbot Uploader)
UPLOADER_API_ID = os.getenv('UPLOADER_API_ID')
UPLOADER_API_HASH = os.getenv('UPLOADER_API_HASH')
UPLOADER_PHONE = os.getenv('UPLOADER_PHONE')

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
