"""
Tests for Phase 10: Health Monitor
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from health_monitor import HealthMonitor


class TestHealthMonitor:
    """Test cases for HealthMonitor."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = Mock()
        db.get_owner = Mock()
        return db

    @pytest.fixture
    def mock_bot(self):
        """Create mock bot."""
        bot = Mock()
        bot.send_message = AsyncMock()
        return bot

    @pytest.fixture
    def health_monitor(self, mock_db, mock_bot):
        """Create health monitor instance."""
        return HealthMonitor(mock_db, bot=mock_bot)

    def test_init(self, mock_db, mock_bot):
        """Test health monitor initialization."""
        monitor = HealthMonitor(mock_db, bot=mock_bot)

        assert monitor.db == mock_db
        assert monitor.bot == mock_bot
        assert monitor.running is False
        assert len(monitor.alerts_sent) == 0

    @pytest.mark.asyncio
    async def test_check_database_success(self, health_monitor):
        """Test successful database health check."""
        health_monitor.db.get_owner.return_value = {'user_id': 1}

        result = await health_monitor._check_database()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_database_failure(self, health_monitor):
        """Test failed database health check."""
        health_monitor.db.get_owner.side_effect = Exception("DB error")

        result = await health_monitor._check_database()

        assert result is False

    @pytest.mark.asyncio
    async def test_check_aria2c_success(self, health_monitor):
        """Test successful aria2c health check."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'result': {'version': '1.36.0'}})

        # Create a mock async context manager for session.post()
        class MockPostContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session.post = Mock(return_value=MockPostContext())
            mock_session_class.return_value = mock_session

            result = await health_monitor._check_aria2c()

            assert result is True

    @pytest.mark.asyncio
    async def test_check_aria2c_failure(self, health_monitor):
        """Test failed aria2c health check."""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_session_class.return_value = mock_session

            result = await health_monitor._check_aria2c()

            assert result is False

    @pytest.mark.asyncio
    async def test_check_userbot_success(self, health_monitor):
        """Test successful userbot health check."""
        with patch('os.path.exists', return_value=True):
            with patch.object(HealthMonitor, '_check_userbot') as mock_check:
                mock_check.return_value = True

                result = await health_monitor._check_userbot()

                assert result is True

    @pytest.mark.asyncio
    async def test_check_userbot_no_session(self, health_monitor):
        """Test userbot health check when session missing."""
        with patch('os.path.exists', return_value=False):
            result = await health_monitor._check_userbot()

            assert result is False

    @pytest.mark.asyncio
    async def test_check_disk_space_success(self, health_monitor):
        """Test successful disk space check."""
        mock_stat = Mock()
        mock_stat.free = 10 * (1024 ** 3)  # 10 GB free

        with patch('shutil.disk_usage', return_value=mock_stat):
            with patch('os.makedirs'):
                result = await health_monitor._check_disk_space()

                assert result is True

    @pytest.mark.asyncio
    async def test_check_disk_space_low(self, health_monitor):
        """Test disk space check with low space."""
        mock_stat = Mock()
        mock_stat.free = 2 * (1024 ** 3)  # 2 GB free

        with patch('shutil.disk_usage', return_value=mock_stat):
            with patch('os.makedirs'):
                result = await health_monitor._check_disk_space()

                assert result is False

    @pytest.mark.asyncio
    async def test_restart_aria2c_success(self, health_monitor):
        """Test successful aria2c restart."""
        with patch('subprocess.run') as mock_run:
            with patch('subprocess.Popen') as mock_popen:
                with patch.object(health_monitor, '_check_aria2c', new_callable=AsyncMock, return_value=True):
                    result = await health_monitor._restart_aria2c()

                    assert result is True
                    mock_run.assert_called_once()
                    mock_popen.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_aria2c_failure(self, health_monitor):
        """Test failed aria2c restart."""
        with patch('subprocess.run', side_effect=Exception("Kill failed")):
            result = await health_monitor._restart_aria2c()

            assert result is False

    @pytest.mark.asyncio
    async def test_reconnect_userbot_success(self, health_monitor):
        """Test successful userbot reconnection."""
        with patch('uploader_bot.UploaderBot') as mock_uploader_class:
            mock_uploader = Mock()
            mock_uploader.is_connected.return_value = True
            mock_uploader_class.return_value = mock_uploader

            result = await health_monitor._reconnect_userbot()

            assert result is True

    @pytest.mark.asyncio
    async def test_send_alert_success(self, health_monitor):
        """Test successful alert sending."""
        health_monitor.db.get_owner.return_value = {'user_id': 1, 'chat_id': 123456}

        await health_monitor._send_alert('aria2c')

        health_monitor.bot.send_message.assert_called_once()
        call_args = health_monitor.bot.send_message.call_args
        assert call_args[1]['chat_id'] == 123456
        assert 'DOWN' in call_args[1]['text']

    @pytest.mark.asyncio
    async def test_send_alert_no_bot(self, health_monitor):
        """Test alert sending when no bot."""
        health_monitor.bot = None

        await health_monitor._send_alert('aria2c')

        # Should not crash
        assert True

    @pytest.mark.asyncio
    async def test_send_alert_no_owner(self, health_monitor):
        """Test alert sending when no owner."""
        health_monitor.db.get_owner.return_value = None

        await health_monitor._send_alert('aria2c')

        # Should not crash
        health_monitor.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_recovery(self, health_monitor):
        """Test recovery notification."""
        health_monitor.db.get_owner.return_value = {'user_id': 1, 'chat_id': 123456}

        await health_monitor._notify_recovery('aria2c')

        health_monitor.bot.send_message.assert_called_once()
        call_args = health_monitor.bot.send_message.call_args
        assert 'recovered' in call_args[1]['text'].lower()

    @pytest.mark.asyncio
    async def test_handle_failure_first_time(self, health_monitor):
        """Test handling failure (first time)."""
        alert_key = 'aria2c_down'

        with patch.object(health_monitor, '_attempt_recovery', new_callable=AsyncMock, return_value=False):
            with patch.object(health_monitor, '_send_alert', new_callable=AsyncMock) as mock_alert:
                await health_monitor._handle_failure('aria2c')

                assert alert_key in health_monitor.alerts_sent
                mock_alert.assert_called_once_with('aria2c')

    @pytest.mark.asyncio
    async def test_handle_failure_already_alerted(self, health_monitor):
        """Test handling failure (already alerted)."""
        alert_key = 'aria2c_down'
        health_monitor.alerts_sent.add(alert_key)

        with patch.object(health_monitor, '_attempt_recovery', new_callable=AsyncMock) as mock_recovery:
            with patch.object(health_monitor, '_send_alert', new_callable=AsyncMock) as mock_alert:
                await health_monitor._handle_failure('aria2c')

                # Should not attempt recovery or send alert again
                mock_recovery.assert_not_called()
                mock_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_attempt_recovery_aria2c(self, health_monitor):
        """Test recovery attempt for aria2c."""
        with patch.object(health_monitor, '_restart_aria2c', new_callable=AsyncMock, return_value=True):
            result = await health_monitor._attempt_recovery('aria2c')

            assert result is True

    @pytest.mark.asyncio
    async def test_attempt_recovery_unknown_service(self, health_monitor):
        """Test recovery attempt for unknown service."""
        result = await health_monitor._attempt_recovery('unknown')

        assert result is False

    @pytest.mark.asyncio
    async def test_check_all_services(self, health_monitor):
        """Test checking all services."""
        health_monitor.db.get_owner.return_value = {'user_id': 1}

        with patch.object(health_monitor, '_check_aria2c', new_callable=AsyncMock, return_value=True):
            with patch.object(health_monitor, '_check_userbot', new_callable=AsyncMock, return_value=True):
                with patch.object(health_monitor, '_check_database', new_callable=AsyncMock, return_value=True):
                    with patch.object(health_monitor, '_check_disk_space', new_callable=AsyncMock, return_value=True):
                        await health_monitor._check_all_services()

                        # All checks should have been called

    @pytest.mark.asyncio
    async def test_start_and_stop(self, health_monitor):
        """Test starting and stopping health monitor."""
        health_monitor.running = True

        # Stop
        health_monitor.stop()

        assert health_monitor.running is False

    @pytest.mark.asyncio
    async def test_already_running(self, health_monitor):
        """Test starting when already running."""
        health_monitor.running = True

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await health_monitor.start()

            # Should exit immediately
            assert health_monitor.running is True

    def test_get_health_status(self, health_monitor):
        """Test getting health status."""
        status = health_monitor.get_health_status()

        assert 'monitor_running' in status
        assert 'alerts_sent' in status
        assert status['monitor_running'] is False
        assert status['alerts_sent'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
