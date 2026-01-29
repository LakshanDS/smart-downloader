"""
Uploader Bot - Phase 8
Userbot client for large file uploads (up to 2 GB).
"""

import logging
import os
from typing import Optional, Dict
from telethon.sync import TelegramClient

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Exception raised when upload fails."""
    pass


class UploaderBot:
    """Userbot client for large file uploads."""

    def __init__(self, api_id: Optional[int] = None, api_hash: Optional[str] = None,
                 phone: Optional[str] = None, session_name: str = 'uploader_bot'):
        """
        Initialize uploader bot.

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            phone: Phone number for the userbot account
            session_name: Name for the session file
        """
        self.api_id = api_id or int(os.getenv('UPLOADER_API_ID', 0))
        self.api_hash = api_hash or os.getenv('UPLOADER_API_HASH', '')
        self.phone = phone or os.getenv('UPLOADER_PHONE', '')
        self.session_name = session_name
        self.client = None
        self._authorized = False

        if self.api_id and self.api_hash:
            self._connect()

    def _connect(self):
        """Initialize Telegram client connection."""
        try:
            self.client = TelegramClient(
                self.session_name,
                api_id=self.api_id,
                api_hash=self.api_hash,
            )

            logger.info(f"Connecting userbot: {self.phone}")

            # Start client
            self.client.connect()

            if not self.client.is_user_authorized():
                logger.warning("Userbot not authorized. Run with --auth to authorize.")
                self._authorized = False
                return False

            logger.info("Userbot connected and authorized!")
            self._authorized = True
            return True

        except Exception as e:
            logger.error(f"Userbot connection failed: {e}")
            raise RuntimeError(f"Could not connect userbot: {str(e)}")

    def is_connected(self) -> bool:
        """Check if userbot is connected and authorized."""
        return bool(self.client and self.client.is_connected() and self._authorized)

    def is_authorized(self) -> bool:
        """Check if userbot is authorized."""
        return self._authorized

    def upload_file(self, file_path: str, caption: Optional[str] = None) -> Optional[Dict]:
        """
        Upload file to 'Saved Messages' (Telegram's cloud storage).

        Args:
            file_path: Path to file to upload
            caption: Optional caption for the file

        Returns:
            Dictionary with file metadata or None on failure
        """
        if not self.is_connected():
            logger.error("Userbot not connected, cannot upload")
            return None

        try:
            logger.info(f"Uploading: {file_path}")

            # Check file exists
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None

            # Upload file to 'me' (Saved Messages)
            message = self.client.send_file(
                'me',
                file_path,
                caption=caption,
                parse_mode='markdown'
            )

            logger.info(f"Upload complete: message_id={message.id}")

            # Extract file metadata
            file_metadata = {
                'message_id': message.id,
                'file_id': None,
                'file_size': None,
                'file_name': None,
                'duration': None
            }

            # Handle video files
            if hasattr(message, 'video') and message.video:
                file_metadata['file_id'] = message.video.id
                file_metadata['file_size'] = message.video.size
                file_metadata['duration'] = message.video.duration if hasattr(message.video, 'duration') else None

            # Handle document files
            elif hasattr(message, 'document') and message.document:
                file_metadata['file_id'] = message.document.id
                file_metadata['file_size'] = message.document.size
                if hasattr(message.document, 'attributes'):
                    for attr in message.document.attributes:
                        if hasattr(attr, 'file_name'):
                            file_metadata['file_name'] = attr.file_name

            # Try to get filename from message
            if hasattr(message, 'file') and message.file:
                if hasattr(message.file, 'name'):
                    file_metadata['file_name'] = message.file.name

            logger.info(f"File metadata: {file_metadata}")
            return file_metadata

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Could not upload file: {str(e)}")

    def delete_file(self, message_id: int) -> bool:
        """
        Delete a file from Saved Messages.

        Args:
            message_id: Message ID to delete

        Returns:
            True if deleted successfully
        """
        if not self.is_connected():
            logger.error("Userbot not connected, cannot delete")
            return False

        try:
            self.client.delete_messages('me', message_id)
            logger.info(f"Deleted message {message_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete message {message_id}: {e}")
            return False

    def get_file_info(self, message_id: int) -> Optional[Dict]:
        """
        Get file information from Saved Messages.

        Args:
            message_id: Message ID to query

        Returns:
            Dictionary with file info or None
        """
        if not self.is_connected():
            return None

        try:
            message = self.client.get_messages('me', ids=message_id)

            if not message:
                return None

            info = {
                'message_id': message.id,
                'date': message.date,
                'caption': message.message if hasattr(message, 'message') else None,
            }

            if hasattr(message, 'video') and message.video:
                info['type'] = 'video'
                info['file_size'] = message.video.size
                info['duration'] = message.video.duration if hasattr(message.video, 'duration') else None

            elif hasattr(message, 'document') and message.document:
                info['type'] = 'document'
                info['file_size'] = message.document.size

            return info

        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
            return None

    def disconnect(self):
        """Close userbot connection."""
        if self.client:
            self.client.disconnect()
            self._authorized = False
            logger.info("Userbot disconnected")

    def get_status(self) -> Dict:
        """
        Get userbot status.

        Returns:
            Dictionary with status info
        """
        return {
            'connected': self.is_connected(),
            'authorized': self.is_authorized(),
            'phone': self.phone,
            'session': self.session_name
        }


# Convenience function for quick access
def get_uploader() -> Optional[UploaderBot]:
    """Get a singleton uploader instance."""
    if not hasattr(get_uploader, '_instance'):
        get_uploader._instance = UploaderBot()
    return get_uploader._instance
