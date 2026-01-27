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

DATABASE_PATH = os.getenv('DATABASE_PATH', 'smart_downloader.db')

# Download settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB in bytes
PROGRESS_UPDATE_INTERVAL = 5  # seconds
RETRY_DELAYS = [0, 120, 480]  # 0s, 2min, 8min (exponential backoff)

# Userbot credentials (for Phase 7 - Userbot Uploader)
UPLOADER_API_ID = os.getenv('UPLOADER_API_ID')
UPLOADER_API_HASH = os.getenv('UPLOADER_API_HASH')
UPLOADER_PHONE = os.getenv('UPLOADER_PHONE')

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
