"""
Cleanup Manager - Phase 7
Auto-clear old bot messages from chats to prevent clutter.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class CleanupManager:
    """Manage automatic chat message cleanup."""

    def __init__(self, db, keep_messages: int = 3):
        """
        Initialize cleanup manager.

        Args:
            db: DatabaseManager instance
            keep_messages: Number of recent messages to keep per chat
        """
        self.db = db
        self.keep_messages = keep_messages
        self.running = False
        self.task = None

    async def check_and_clean_chats(self):
        """Check all chats for cleanup eligibility."""
        try:
            # Get chats that need cleanup (inactive for specified hours)
            chats_to_clear = self.get_chats_to_clear(hours=24)

            if not chats_to_clear:
                logger.debug("No chats require cleanup")
                return

            logger.info(f"Found {len(chats_to_clear)} chats to clean")

            for chat_id in chats_to_clear:
                await self._cleanup_chat(chat_id)

        except Exception as e:
            logger.error(f"Error checking chats for cleanup: {e}")

    def get_chats_to_clear(self, hours: int = 24) -> List[int]:
        """
        Get list of chat IDs that need cleanup.

        Args:
            hours: Inactivity threshold in hours

        Returns:
            List of chat IDs to clean
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                threshold = datetime.now() - timedelta(hours=hours)

                cursor.execute("""
                    SELECT DISTINCT chat_id
                    FROM activity_log
                    WHERE auto_clear_enabled = 1
                    AND last_activity < ?
                """, (threshold.isoformat(),))

                chats = [row[0] for row in cursor.fetchall()]
                return chats

        except Exception as e:
            logger.error(f"Error getting chats to clear: {e}")
            return []

    async def _cleanup_chat(self, chat_id: int, bot_client=None):
        """
        Clean messages for a specific chat.

        Args:
            chat_id: Telegram chat ID
            bot_client: Optional bot client for message deletion
        """
        try:
            # Get bot's messages in chat
            messages = await self._get_bot_messages(chat_id, bot_client)

            if not messages:
                logger.debug(f"No messages to clean for chat {chat_id}")
                return

            # Check if we have enough to keep
            if len(messages) <= self.keep_messages:
                logger.debug(f"Chat {chat_id} only has {len(messages)} messages, skipping")
                return

            # Delete all but last N messages
            to_delete = messages[:-self.keep_messages]  # Keep last N

            for msg_id in to_delete:
                deleted = await self._delete_bot_message(chat_id, msg_id, bot_client)
                if deleted:
                    logger.debug(f"Deleted message {msg_id} from chat {chat_id}")

            # Update last_activity (prevents re-cleaning too soon)
            self._update_chat_activity(chat_id)

            logger.info(f"Cleaned {len(to_delete)} messages from chat {chat_id}")

        except Exception as e:
            logger.error(f"Error cleaning chat {chat_id}: {e}")

    async def _get_bot_messages(self, chat_id: int, bot_client=None) -> List[int]:
        """
        Get bot's message IDs from a chat.

        Args:
            chat_id: Telegram chat ID
            bot_client: Optional bot client

        Returns:
            List of message IDs
        """
        # This would use python-telegram-bot's get_chat_history
        # For now, return empty list (implementation depends on bot client)
        return []

    async def _delete_bot_message(self, chat_id: int, message_id: int, bot_client=None) -> bool:
        """
        Delete a specific bot message.

        Args:
            chat_id: Telegram chat ID
            message_id: Telegram message ID
            bot_client: Optional bot client

        Returns:
            True if deleted successfully
        """
        # This would use python-telegram-bot's delete_message
        # For now, return False (implementation depends on bot client)
        return False

    def _update_chat_activity(self, chat_id: int):
        """
        Update chat activity timestamp.

        Args:
            chat_id: Telegram chat ID
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE activity_log
                    SET last_activity = ?
                    WHERE chat_id = ?
                """, (datetime.now().isoformat(), chat_id))
                conn.commit()

        except Exception as e:
            logger.error(f"Error updating chat activity: {e}")

    async def start(self, interval_minutes: int = 60):
        """
        Start background cleanup task.

        Args:
            interval_minutes: Check interval in minutes
        """
        if self.running:
            logger.warning("Cleanup manager already running")
            return

        self.running = True
        logger.info(f"Starting cleanup manager (checks every {interval_minutes} minutes)")

        while self.running:
            try:
                await self.check_and_clean_chats()
                await asyncio.sleep(interval_minutes * 60)  # Convert to seconds

            except asyncio.CancelledError:
                logger.info("Cleanup manager stopped")
                break
            except Exception as e:
                logger.error(f"Cleanup manager error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    def stop(self):
        """Stop cleanup manager."""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("Cleanup manager stopped")

    def get_status(self) -> dict:
        """
        Get current cleanup status.

        Returns:
            Dictionary with status info
        """
        return {
            'running': self.running,
            'keep_messages': self.keep_messages,
            'chats_pending': len(self.get_chats_to_clear())
        }
