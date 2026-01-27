# Phase 9: Monitoring & Recovery

**Objective:** Server health monitoring, auto-recovery of failed services, and error tracking.

## Architecture

```
Background Monitor (every 30s)
       │
       ├─────────────────────────────────────┐
       │  Health Checks                     │
       │  - aria2c RPC server               │
       │  - Userbot connection              │
       │  - Database health                 │
       │  - Disk space                      │
       └─────────────────────────────────────┘
       │
       ├─────────────────────────────────────┐
       │  Auto-Recovery                     │
       │  - Restart failed services         │
       │  - Reconnect userbot               │
       │  - Alert owner                     │
       └─────────────────────────────────────┘
```

## Key Features

- **Health checks**: Monitor all critical services
- **Auto-recovery**: Restart failed services automatically
- **Alerting**: Notify owner of issues
- **Error tracking**: Log failures for debugging

## Components

### 1. Health Monitor (`health_monitor.py`)

```python
import asyncio
import logging
import subprocess
import os
from typing import Dict, List
from datetime import datetime
from database import DatabaseManager

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Monitor server health and auto-recover from failures."""

    CHECK_INTERVAL = 30  # seconds
    ARIA2C_PORT = 6800

    def __init__(self, db: DatabaseManager, bot=None):
        self.db = db
        self.bot = bot
        self.running = False
        self.alerts_sent = set()  # Track alerts to avoid spam

    async def start(self):
        """Start background health monitor."""
        if self.running:
            return

        self.running = True
        logger.info("Starting health monitor...")

        while self.running:
            try:
                await self._check_all_services()
                await asyncio.sleep(self.CHECK_INTERVAL)

            except asyncio.CancelledError:
                logger.info("Health monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}", exc_info=True)
                await asyncio.sleep(60)

    def stop(self):
        """Stop health monitor."""
        self.running = False

    async def _check_all_services(self):
        """Run all health checks."""
        checks = {
            'aria2c': self._check_aria2c,
            'userbot': self._check_userbot,
            'database': self._check_database,
            'disk_space': self._check_disk_space,
        }

        for service, check_func in checks.items():
            try:
                is_healthy = await check_func()

                if not is_healthy:
                    await self._handle_failure(service)
                else:
                    # Reset alert if service recovered
                    alert_key = f"{service}_down"
                    if alert_key in self.alerts_sent:
                        self.alerts_sent.remove(alert_key)
                        await self._notify_recovery(service)

            except Exception as e:
                logger.error(f"Health check failed for {service}: {e}")

    async def _check_aria2c(self) -> bool:
        """Check if aria2c RPC server is running."""
        try:
            import aiohttp

            url = f"http://localhost:{self.ARIA2C_PORT}/jsonrpc"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"jsonrpc": "2.0", "id": "health", "method": "aria2.getVersion"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'result' in data:
                            logger.debug("aria2c is healthy")
                            return True

            return False

        except Exception as e:
            logger.warning(f"aria2c health check failed: {e}")
            return False

    async def _check_userbot(self) -> bool:
        """Check if userbot is connected."""
        try:
            # Check if session file exists
            session_file = 'uploader_bot.session'

            if not os.path.exists(session_file):
                logger.warning("Userbot session file not found")
                return False

            # Try to get userbot client status
            from uploader_bot import UploaderBot

            uploader = UploaderBot()

            if uploader.client and uploader.client.is_connected():
                logger.debug("Userbot is healthy")
                return True

            return False

        except Exception as e:
            logger.warning(f"Userbot health check failed: {e}")
            return False

    async def _check_database(self) -> bool:
        """Check if database is accessible."""
        try:
            # Try to query database
            owner = self.db.get_owner()
            logger.debug("Database is healthy")
            return True

        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False

    async def _check_disk_space(self) -> bool:
        """Check if disk has enough space."""
        try:
            import shutil

            # Check /tmp downloads directory
            download_dir = '/tmp/downloads'
            os.makedirs(download_dir, exist_ok=True)

            stat = shutil.disk_usage(download_dir)
            free_gb = stat.free / (1024 ** 3)

            # Warn if less than 5GB free
            if free_gb < 5:
                logger.warning(f"Low disk space: {free_gb:.2f} GB free")
                return False

            logger.debug(f"Disk space OK: {free_gb:.2f} GB free")
            return True

        except Exception as e:
            logger.warning(f"Disk space check failed: {e}")
            return False

    async def _handle_failure(self, service: str):
        """Handle service failure."""
        alert_key = f"{service}_down"

        # Avoid spamming alerts
        if alert_key in self.alerts_sent:
            return

        self.alerts_sent.add(alert_key)
        logger.error(f"Service {service} is DOWN!")

        # Attempt recovery
        recovered = await self._attempt_recovery(service)

        if not recovered:
            # Notify owner
            await self._send_alert(service)

    async def _attempt_recovery(self, service: str) -> bool:
        """Attempt to recover a failed service."""
        logger.info(f"Attempting recovery for {service}...")

        try:
            if service == 'aria2c':
                return await self._restart_aria2c()

            elif service == 'userbot':
                return await self._reconnect_userbot()

            elif service == 'database':
                # Can't auto-recover database
                return False

            elif service == 'disk_space':
                # Can't auto-recover disk space
                return False

        except Exception as e:
            logger.error(f"Recovery attempt failed for {service}: {e}")

        return False

    async def _restart_aria2c(self) -> bool:
        """Restart aria2c RPC server."""
        try:
            # Kill existing aria2c
            subprocess.run(['pkill', 'aria2c'], timeout=5)

            await asyncio.sleep(2)

            # Start aria2c
            subprocess.Popen([
                'aria2c',
                '--enable-rpc',
                f'--rpc-listen-port={self.ARIA2C_PORT}',
                '--rpc-allow-public=true',
                '--daemon=true'
            ])

            await asyncio.sleep(3)

            # Check if it's running
            if await self._check_aria2c():
                logger.info("aria2c restarted successfully")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to restart aria2c: {e}")
            return False

    async def _reconnect_userbot(self) -> bool:
        """Reconnect userbot."""
        try:
            from uploader_bot import UploaderBot

            uploader = UploaderBot()

            if uploader.client:
                uploader.client.connect()

                if uploader.client.is_user_authorized():
                    logger.info("Userbot reconnected successfully")
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to reconnect userbot: {e}")
            return False

    async def _send_alert(self, service: str):
        """Send alert to bot owner."""
        if not self.bot:
            return

        owner = self.db.get_owner()
        if not owner:
            return

        alert_messages = {
            'aria2c': "⚠️ **aria2c RPC Server is DOWN**\n\nCannot process torrent downloads. Attempting auto-recovery...",
            'userbot': "⚠️ **Userbot is DISCONNECTED**\n\nCannot upload files to Telegram. Attempting to reconnect...",
            'database': "⚠️ **Database is INACCESSIBLE**\n\nCannot read/write data. Please check the database file.",
            'disk_space': "⚠️ **Low Disk Space**\n\nLess than 5GB free. Downloads may fail.",
        }

        message = alert_messages.get(
            service,
            f"⚠️ Service **{service}** is not healthy"
        )

        try:
            await self.bot.send_message(
                chat_id=owner['chat_id'],
                text=message
            )
            logger.info(f"Alert sent for {service}")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")

    async def _notify_recovery(self, service: str):
        """Notify owner that service recovered."""
        if not self.bot:
            return

        owner = self.db.get_owner()
        if not owner:
            return

        message = f"✅ **{service}** has recovered!"

        try:
            await self.bot.send_message(
                chat_id=owner['chat_id'],
                text=message
            )
        except Exception as e:
            logger.error(f"Failed to send recovery notification: {e}")
```

### 2. Integration with Bot

```python
# In bot.py
from health_monitor import HealthMonitor

# Start health monitor
async def main():
    # ... existing setup ...

    # Start health monitor after bot is ready
    health_monitor = HealthMonitor(db=db, bot=bot)
    asyncio.create_task(health_monitor.start())

    # Run bot
    await app.run_polling()
```

## Configuration

```python
# config.py
HEALTH_CHECK_INTERVAL = 30  # seconds
ARIA2C_PORT = 6800
MIN_DISK_SPACE_GB = 5  # Alert if less than this
```

## Implementation Tasks

- [ ] Create `health_monitor.py` with HealthMonitor class
- [ ] Implement aria2c health check
- [ ] Implement userbot health check
- [ ] Implement database health check
- [ ] Implement disk space check
- [ ] Add aria2c auto-restart
- [ ] Add userbot reconnect
- [ ] Implement alert notifications
- [ ] Test failure scenarios
- [ ] Test auto-recovery

## Dependencies

```python
# requirements.txt additions
aiohttp>=3.8.0
```

## Notes

- **Check interval**: Every 30 seconds (configurable)
- **Alert throttling**: Only send one alert per failure
- **Auto-recovery**: Restart aria2c, reconnect userbot
- **Database issues**: Manual intervention required
- **Logging**: All health checks logged

## Failure Scenarios

| Service | Failure | Recovery |
|---------|---------|----------|
| aria2c | RPC not responding | Auto-restart |
| userbot | Session disconnected | Auto-reconnect |
| database | File locked/missing | Manual (alert only) |
| disk | <5GB free | Manual (alert only) |
