"""
Tests for Phase 8: Uploader Bot & Upload Manager
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from uploader_bot import UploaderBot, UploadError
from upload_manager import UploadManager


class TestUploaderBot:
    """Test cases for UploaderBot."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Telegram client."""
        client = Mock()
        client.connect = Mock()
        client.is_user_authorized = Mock(return_value=True)
        client.is_connected = Mock(return_value=True)
        client.send_file = Mock()
        client.delete_messages = Mock()
        client.get_messages = Mock()
        client.disconnect = Mock()
        return client

    @pytest.fixture
    def uploader_bot(self, mock_client):
        """Create uploader bot instance."""
        bot = UploaderBot(api_id=12345, api_hash='test_hash', phone='+1234567890')
        bot.client = mock_client
        bot._authorized = True
        return bot

    def test_init(self):
        """Test uploader bot initialization."""
        bot = UploaderBot(api_id=12345, api_hash='test_hash', phone='+1234567890')

        assert bot.api_id == 12345
        assert bot.api_hash == 'test_hash'
        assert bot.phone == '+1234567890'
        assert bot.session_name == 'uploader_bot'

    def test_is_connected_true(self, uploader_bot):
        """Test is_connected when connected."""
        uploader_bot.client.is_connected.return_value = True
        assert uploader_bot.is_connected() is True

    def test_is_connected_false(self, uploader_bot):
        """Test is_connected when not connected."""
        uploader_bot.client = None
        assert uploader_bot.is_connected() is False

    def test_is_authorized_true(self, uploader_bot):
        """Test is_authorized when authorized."""
        uploader_bot._authorized = True
        assert uploader_bot.is_authorized() is True

    def test_upload_file_success(self, uploader_bot):
        """Test successful file upload."""
        mock_message = Mock()
        mock_message.id = 123
        mock_message.video = Mock()
        mock_message.video.id = 'video_id_123'
        mock_message.video.size = 1024000
        mock_message.video.duration = 120
        uploader_bot.client.send_file.return_value = mock_message

        with patch('os.path.exists', return_value=True):
            result = uploader_bot.upload_file('/path/to/file.mp4')

        assert result is not None
        assert result['message_id'] == 123
        assert result['file_id'] == 'video_id_123'
        assert result['file_size'] == 1024000
        assert result['duration'] == 120

    def test_upload_file_not_found(self, uploader_bot):
        """Test upload when file doesn't exist."""
        with patch('os.path.exists', return_value=False):
            result = uploader_bot.upload_file('/nonexistent/file.mp4')

        assert result is None

    def test_upload_file_not_connected(self, uploader_bot):
        """Test upload when not connected."""
        uploader_bot.client = None
        result = uploader_bot.upload_file('/path/to/file.mp4')

        assert result is None

    def test_delete_file_success(self, uploader_bot):
        """Test successful file deletion."""
        result = uploader_bot.delete_file(123)

        assert result is True
        uploader_bot.client.delete_messages.assert_called_once_with('me', 123)

    def test_delete_file_not_connected(self, uploader_bot):
        """Test delete when not connected."""
        uploader_bot.client = None
        result = uploader_bot.delete_file(123)

        assert result is False

    def test_get_file_info_success(self, uploader_bot):
        """Test getting file info."""
        mock_message = Mock()
        mock_message.id = 123
        mock_message.date = datetime.now()
        mock_message.video = Mock()
        mock_message.video.size = 1024000
        mock_message.video.duration = 120
        uploader_bot.client.get_messages.return_value = mock_message

        info = uploader_bot.get_file_info(123)

        assert info is not None
        assert info['message_id'] == 123
        assert info['type'] == 'video'

    def test_disconnect(self, uploader_bot):
        """Test disconnecting uploader bot."""
        uploader_bot.disconnect()

        assert uploader_bot._authorized is False
        uploader_bot.client.disconnect.assert_called_once()

    def test_get_status(self, uploader_bot):
        """Test getting uploader status."""
        status = uploader_bot.get_status()

        assert 'connected' in status
        assert 'authorized' in status
        assert 'phone' in status
        assert 'session' in status


class TestUploadManager:
    """Test cases for UploadManager."""

    @pytest.fixture
    def mock_uploader(self):
        """Create mock uploader bot."""
        uploader = Mock()
        uploader.is_connected.return_value = True
        uploader.is_authorized.return_value = True
        uploader.upload_file = Mock()
        uploader.get_status.return_value = {'connected': True}
        uploader.disconnect = Mock()
        return uploader

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = Mock()
        db.update_media_file_id = Mock()
        db.update_media_status = Mock()
        return db

    @pytest.fixture
    def upload_manager(self, mock_uploader, mock_db):
        """Create upload manager instance."""
        manager = UploadManager(db=mock_db)
        manager.uploader = mock_uploader
        return manager

    def test_init(self, mock_db):
        """Test upload manager initialization."""
        manager = UploadManager(api_id=12345, api_hash='test', phone='+123456', db=mock_db)

        assert manager.db == mock_db
        assert manager.uploading is False
        assert manager.queue == []

    def test_queue_upload_success(self, upload_manager):
        """Test successful queue upload."""
        result = upload_manager.queue_upload('/path/to/file.mp4', 123)

        assert result is True
        assert len(upload_manager.queue) == 1
        assert upload_manager.queue[0]['file_path'] == '/path/to/file.mp4'
        assert upload_manager.queue[0]['media_id'] == 123

    def test_queue_upload_invalid(self, upload_manager):
        """Test queue upload with invalid params."""
        result = upload_manager.queue_upload('', 123)

        assert result is False
        assert len(upload_manager.queue) == 0

    def test_queue_uploads(self, upload_manager):
        """Test queueing multiple uploads."""
        uploads = [
            {'file_path': '/file1.mp4', 'media_id': 1},
            {'file_path': '/file2.mp4', 'media_id': 2},
        ]

        count = upload_manager.queue_uploads(uploads)

        assert count == 2
        assert len(upload_manager.queue) == 2

    @pytest.mark.asyncio
    async def test_process_queue_empty(self, upload_manager):
        """Test processing empty queue."""
        await upload_manager.process_queue()

        assert upload_manager.uploading is False

    @pytest.mark.asyncio
    async def test_process_queue_with_items(self, upload_manager):
        """Test processing queue with items."""
        upload_manager.queue_upload('/path/to/file.mp4', 123)

        mock_result = {'message_id': 456, 'file_id': 'vid123'}
        upload_manager.uploader.upload_file.return_value = mock_result

        with patch('os.path.exists', return_value=True):
            await upload_manager.process_queue()

        assert len(upload_manager.queue) == 0
        upload_manager.db.update_media_file_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_queue_upload_failure(self, upload_manager):
        """Test handling upload failure."""
        upload_manager.queue_upload('/path/to/file.mp4', 123)

        upload_manager.uploader.upload_file.side_effect = UploadError("Upload failed")

        with patch('os.path.exists', return_value=True):
            await upload_manager.process_queue()

        assert len(upload_manager.queue) == 0
        upload_manager.db.update_media_status.assert_called_once_with(123, 'failed', 'Upload failed')

    @pytest.mark.asyncio
    async def test_start_processor(self, upload_manager):
        """Test starting upload processor."""
        with patch.object(upload_manager, 'process_queue', new_callable=AsyncMock):
            await upload_manager.start_processor(check_interval=1)

            # Sleep briefly to let processor start
            await asyncio.sleep(0.1)

            assert upload_manager.current_task is not None

            # Clean up
            await upload_manager.stop_processor()

    @pytest.mark.asyncio
    async def test_stop_processor(self, upload_manager):
        """Test stopping upload processor."""
        upload_manager.current_task = Mock()
        await upload_manager.stop_processor()

        assert upload_manager._stop_event.is_set()
        assert upload_manager.uploading is False

    def test_get_status(self, upload_manager):
        """Test getting upload manager status."""
        status = upload_manager.get_status()

        assert 'queue_size' in status
        assert 'uploading' in status
        assert 'uploader_status' in status
        assert status['queue_size'] == 0
        assert status['uploading'] is False

    def test_clear_queue(self, upload_manager):
        """Test clearing upload queue."""
        upload_manager.queue_upload('/file1.mp4', 1)
        upload_manager.queue_upload('/file2.mp4', 2)

        count = upload_manager.clear_queue()

        assert count == 2
        assert len(upload_manager.queue) == 0

    def test_disconnect(self, upload_manager):
        """Test disconnecting upload manager."""
        upload_manager.disconnect()

        upload_manager.uploader.disconnect.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
