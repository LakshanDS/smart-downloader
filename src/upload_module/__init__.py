"""
Upload Module - Smart Downloader

Separate upload system that watches database for completed downloads
and uploads them to Telegram via userbot.

Components:
- UploaderBot: Userbot client for Telegram uploads
- UploadManager: Database watcher and upload processor
"""

from upload_module.uploader_bot import UploaderBot, UploadError, get_uploader
from upload_module.upload_manager import UploadManager

__all__ = [
    'UploaderBot',
    'UploadError',
    'get_uploader',
    'UploadManager',
]
