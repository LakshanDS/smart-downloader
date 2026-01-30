"""
Upload Handler - Smart Downloader Pooler

Handle Telegram uploads using bot or userbot.
Prefers userbot for larger files, falls back to bot.
"""

import asyncio
import logging
import os
from typing import Optional, Dict
from telegram import Bot
from pathlib import Path

logger = logging.getLogger(__name__)


class UploadHandler:
    """
    Upload Handler - Telegram Uploads

    Handles uploading files to Telegram using:
    - Userbot (preferred) - for larger files, no size limit
    - Bot API (fallback) - for files under 2GB
    """

    def __init__(self, db, bot_token: str, bot_instance: Bot = None,
                 userbot_api_id: str = None, userbot_api_hash: str = None,
                 userbot_phone: str = None):
        """
        Initialize upload handler.

        Args:
            db: Database manager instance
            bot_token: Telegram bot token
            bot_instance: Existing Bot instance (optional)
            userbot_api_id: Userbot API ID (optional)
            userbot_api_hash: Userbot API hash (optional)
            userbot_phone: Userbot phone number (optional)
        """
        self.db = db
        self.bot_token = bot_token
        self.bot = bot_instance or Bot(token=bot_token)
        self.userbot = None

        # Try to initialize userbot if credentials provided
        if userbot_api_id and userbot_api_hash and userbot_phone:
            self._init_userbot(userbot_api_id, userbot_api_hash, userbot_phone)

    def _init_userbot(self, api_id: str, api_hash: str, phone: str):
        """Initialize userbot client."""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            # Use string session if available
            session_name = f'sessions/{phone}'
            os.makedirs(os.path.dirname(session_name), exist_ok=True)

            self.userbot = TelegramClient(session_name, api_id, api_hash)
            logger.info(f"Userbot initialized: {phone}")

        except ImportError:
            logger.warning("Telethon not installed, userbot unavailable")
            self.userbot = None
        except Exception as e:
            logger.error(f"Failed to initialize userbot: {e}")
            self.userbot = None

    async def upload(self, download_id: int, file_path: str,
                    caption: str = None, chat_id: int = None) -> Optional[str]:
        """
        Upload file to Telegram.

        Args:
            download_id: Database download ID
            file_path: Path to downloaded file
            caption: Optional caption
            chat_id: Target chat ID (for saved messages)

        Returns:
            Telegram file_id if successful, None otherwise
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        file_size = os.path.getsize(file_path)

        # Update status to uploading
        self.db.update_download_status(download_id, 'uploading')

        logger.info(f"Uploading {file_path} ({file_size / (1024**2):.1f} MB)")

        try:
            file_id = None

            # Try userbot first (preferred)
            if self.userbot:
                file_id = await self._upload_userbot(
                    download_id, file_path, caption, chat_id
                )

            # Fallback to bot API
            if not file_id:
                file_id = await self._upload_bot(
                    download_id, file_path, caption, chat_id
                )

            if file_id:
                # Update database with file_id and mark as uploaded
                self.db.update_download_file_id(
                    download_id,
                    file_id=file_id,
                    file_path=file_path
                )
                logger.info(f"Upload complete: {download_id} -> {file_id}")

                # Delete local file after successful upload
                self._delete_file(file_path)

                return file_id
            else:
                raise Exception("Both userbot and bot upload failed")

        except Exception as e:
            logger.error(f"Upload failed for {download_id}: {e}")
            self.db.update_download_status(
                download_id,
                'downloaded',  # Revert to downloaded so upload can retry
                error_message=f"Upload failed: {str(e)}"
            )
            return None

    async def _upload_userbot(self, download_id: int, file_path: str,
                            caption: str = None, chat_id: int = None) -> Optional[str]:
        """
        Upload using userbot (Telethon).

        Args:
            download_id: Database download ID
            file_path: Path to file
            caption: Optional caption
            chat_id: Target chat ID

        Returns:
            File ID or None
        """
        if not self.userbot:
            return None

        try:
            # Connect userbot if not connected
            if not self.userbot.is_connected():
                await self.userbot.connect()

                # Check if authorized
                if not await self.userbot.is_user_authorized():
                    logger.warning("Userbot not authorized, please run setup")
                    return None

            # Get target chat (saved messages = me)
            target = await self.userbot.get_me() if not chat_id else chat_id

            # Upload file
            message = await self.userbot.send_file(
                entity=target,
                file=file_path,
                caption=caption,
                progress_callback=lambda sent, total: self._upload_progress(
                    download_id, sent, total
                )
            )

            # Extract file_id from message
            if message.file:
                return str(message.file.id)

            return None

        except Exception as e:
            logger.error(f"Userbot upload failed: {e}")
            return None

    async def _upload_bot(self, download_id: int, file_path: str,
                         caption: str = None, chat_id: int = None) -> Optional[str]:
        """
        Upload using bot API.

        Args:
            download_id: Database download ID
            file_path: Path to file
            caption: Optional caption
            chat_id: Target chat ID

        Returns:
            File ID or None
        """
        try:
            # For bot, upload to user's chat_id or owner's chat
            if not chat_id:
                owner = self.db.get_owner()
                if not owner:
                    logger.error("No owner found, cannot upload via bot")
                    return None
                chat_id = owner['chat_id']

            # Determine file type
            file_ext = Path(file_path).suffix.lower()
            video_exts = {'.mp4', '.mkv', '.webm', '.avi', '.mov'}
            audio_exts = {'.mp3', '.m4a', '.aac', '.flac', '.ogg', '.wav'}

            # Send file with progress
            with open(file_path, 'rb') as f:
                if file_ext in video_exts:
                    message = await self.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=caption,
                        write_timeout=600,
                        read_timeout=600,
                        connect_timeout=60
                    )
                elif file_ext in audio_exts:
                    message = await self.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        caption=caption,
                        write_timeout=600,
                        read_timeout=600,
                        connect_timeout=60
                    )
                else:
                    message = await self.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        caption=caption,
                        write_timeout=600,
                        read_timeout=600,
                        connect_timeout=60
                    )

            # Extract file_id
            if message.video:
                return message.video.file_id
            elif message.audio:
                return message.audio.file_id
            elif message.document:
                return message.document.file_id

            return None

        except Exception as e:
            logger.error(f"Bot upload failed: {e}")
            return None

    def _upload_progress(self, download_id: int, sent: int, total: int):
        """Update upload progress in database."""
        if total > 0:
            progress = int((sent / total) * 100)
            self.db.update_progress(
                download_id,
                progress=progress,
                upload_speed=0,  # Could calculate if tracking time
                eta_seconds=0
            )

    async def disconnect(self):
        """Disconnect userbot if connected."""
        if self.userbot and self.userbot.is_connected():
            await self.userbot.disconnect()
            logger.info("Userbot disconnected")

    def _delete_file(self, file_path: str):
        """
        Delete local file after successful upload.

        Args:
            file_path: Path to file to delete
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted local file: {file_path}")

                # Also try to remove empty parent directories
                parent_dir = os.path.dirname(file_path)
                try:
                    if parent_dir and not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                        logger.info(f"Removed empty directory: {parent_dir}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to delete file {file_path}: {e}")
