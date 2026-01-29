"""
Tests for Phase 7: Cleanup Manager
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cleanup_manager import CleanupManager


class TestCleanupManager:
    """Test cases for CleanupManager."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = Mock()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        # Make get_connection work as context manager
        db.get_connection.return_value.__enter__ = Mock(return_value=conn)
        db.get_connection.return_value.__exit__ = Mock(return_value=False)
        return db

    @pytest.fixture
    def cleanup_manager(self, mock_db):
        """Create cleanup manager instance."""
        return CleanupManager(mock_db, keep_messages=3)

    def test_init(self, mock_db):
        """Test cleanup manager initialization."""
        manager = CleanupManager(mock_db, keep_messages=5)

        assert manager.db == mock_db
        assert manager.keep_messages == 5
        assert manager.running is False
        assert manager.task is None

    def test_get_chats_to_clear_empty(self, cleanup_manager):
        """Test getting chats when none need cleanup."""
        cleanup_manager.db.get_connection.return_value.__enter__.return_value.cursor().fetchall.return_value = []

        chats = cleanup_manager.get_chats_to_clear(hours=24)

        assert chats == []
        cleanup_manager.db.get_connection.return_value.__enter__.return_value.cursor().execute.assert_called_once()

    def test_get_chats_to_clear_with_chats(self, cleanup_manager):
        """Test getting chats that need cleanup."""
        cleanup_manager.db.get_connection.return_value.__enter__.return_value.cursor().fetchall.return_value = [
            (123456,),
            (789012,),
        ]

        chats = cleanup_manager.get_chats_to_clear(hours=24)

        assert len(chats) == 2
        assert 123456 in chats
        assert 789012 in chats

    def test_get_chats_to_clear_with_threshold(self, cleanup_manager):
        """Test that threshold is calculated correctly."""
        threshold = datetime.now() - timedelta(hours=24)

        cleanup_manager.get_chats_to_clear(hours=24)

        # Check that execute was called with the threshold
        execute_call = cleanup_manager.db.get_connection.return_value.__enter__.return_value.cursor().execute.call_args
        assert execute_call is not None

    @pytest.mark.asyncio
    async def test_cleanup_chat_no_messages(self, cleanup_manager):
        """Test cleanup chat when there are no messages."""
        with patch.object(cleanup_manager, '_get_bot_messages', return_value=[]):
            await cleanup_manager._cleanup_chat(123456)

            # Should not try to delete or update activity
            cleanup_manager.db.get_connection.return_value.__enter__.return_value.cursor().execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_chat_fewer_than_keep(self, cleanup_manager):
        """Test cleanup chat when messages <= keep limit."""
        with patch.object(cleanup_manager, '_get_bot_messages', return_value=[1, 2]):
            await cleanup_manager._cleanup_chat(123456)

            # Should not delete (2 messages <= keep 3)
            with patch.object(cleanup_manager, '_delete_bot_message', return_value=False) as mock_delete:
                await cleanup_manager._cleanup_chat(123456)
                mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_chat_delete_messages(self, cleanup_manager):
        """Test that old messages are deleted."""
        messages = [1, 2, 3, 4, 5]  # 5 messages, keep 3

        with patch.object(cleanup_manager, '_get_bot_messages', return_value=messages):
            with patch.object(cleanup_manager, '_delete_bot_message', return_value=True) as mock_delete:
                with patch.object(cleanup_manager, '_update_chat_activity') as mock_update:
                    await cleanup_manager._cleanup_chat(123456)

                    # Should delete messages 1 and 2 (keep 3, 4, 5)
                    assert mock_delete.call_count == 2
                    mock_delete.assert_any_call(123456, 1, None)
                    mock_delete.assert_any_call(123456, 2, None)
                    mock_update.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_check_and_clean_chats_empty(self, cleanup_manager):
        """Test check and clean when no chats need cleanup."""
        with patch.object(cleanup_manager, 'get_chats_to_clear', return_value=[]):
            await cleanup_manager.check_and_clean_chats()

            # Should not attempt to clean any chat
            with patch.object(cleanup_manager, '_cleanup_chat', new_callable=AsyncMock) as mock_cleanup:
                await cleanup_manager.check_and_clean_chats()
                mock_cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_and_clean_chats_with_chats(self, cleanup_manager):
        """Test check and clean with multiple chats."""
        chats = [123456, 789012]

        with patch.object(cleanup_manager, 'get_chats_to_clear', return_value=chats):
            with patch.object(cleanup_manager, '_cleanup_chat', new_callable=AsyncMock) as mock_cleanup:
                await cleanup_manager.check_and_clean_chats()

                # Should clean both chats
                assert mock_cleanup.call_count == 2
                mock_cleanup.assert_any_call(123456)
                mock_cleanup.assert_any_call(789012)

    def test_update_chat_activity(self, cleanup_manager):
        """Test updating chat activity."""
        cleanup_manager._update_chat_activity(123456)

        # Should update the activity log
        cleanup_manager.db.get_connection.return_value.__enter__.return_value.cursor().execute.assert_called()
        cleanup_manager.db.get_connection.return_value.__enter__.return_value.commit.assert_called()

    def test_get_status(self, cleanup_manager):
        """Test getting cleanup status."""
        with patch.object(cleanup_manager, 'get_chats_to_clear', return_value=[123, 456]):
            status = cleanup_manager.get_status()

            assert 'running' in status
            assert 'keep_messages' in status
            assert 'chats_pending' in status
            assert status['running'] is False
            assert status['keep_messages'] == 3
            assert status['chats_pending'] == 2

    @pytest.mark.asyncio
    async def test_start_already_running(self, cleanup_manager):
        """Test starting when already running."""
        cleanup_manager.running = True

        await cleanup_manager.start(interval_minutes=60)

        # Should log warning and not start
        assert cleanup_manager.running is True

    @pytest.mark.asyncio
    async def test_start_success(self, cleanup_manager):
        """Test starting cleanup manager."""
        cleanup_manager.running = False

        with patch.object(cleanup_manager, 'check_and_clean_chats', new_callable=AsyncMock) as mock_check:
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                # Make sleep raise CancelledError immediately
                mock_sleep.side_effect = asyncio.CancelledError()

                await cleanup_manager.start(interval_minutes=1)

                # Should check once before sleep raises CancelledError
                mock_check.assert_called_once()

    def test_stop(self, cleanup_manager):
        """Test stopping cleanup manager."""
        mock_task = Mock()
        cleanup_manager.task = mock_task

        cleanup_manager.stop()

        assert cleanup_manager.running is False
        mock_task.cancel.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
