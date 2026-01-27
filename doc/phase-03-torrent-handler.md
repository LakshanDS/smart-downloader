# Phase 3: Torrent Handler (aria2c)

**Objective:** Integrate aria2c RPC for magnet/torrent downloads with real-time progress tracking.

## Architecture

```
Bot Command (torrent)
       │
       │ Parses magnet link
       ↓
┌────────────────────────┐
│  Torrent Manager      │
│  - Validate magnet     │
│  - Queue with aria2c │
│  - Track progress    │
└────────────────────────┘
       │
       ↓
┌────────────────────────┐
│  aria2c RPC Server   │
│  (localhost:6800)    │
│  - Download files    │
│  - Report progress   │
└────────────────────────┘
       │
       ↓ Updates database every 5s
┌────────────────────────┐
│  Database            │
│  - Update progress    │
│  - Mark complete    │
└────────────────────────┘
```

## Components

### 1. aria2c Setup (`torrent_manager.py`)

```python
import aria2p
import time
import asyncio
from typing import Dict, Callable, Optional
from database import DatabaseManager

class TorrentManager:
    """Manage aria2c RPC for torrent downloads."""
    
    def __init__(self, rpc_url: str = "http://localhost:6800/jsonrpc",
                 db: DatabaseManager = None):
        self.rpc_url = rpc_url
        self.db = db
        self.aria = aria2p.API(rpc_url)
        self.active_downloads: Dict[str, Dict] = {}
    
    def check_connection(self) -> bool:
        """Verify aria2c RPC is running."""
        try:
            version = self.aria.get_global_stat()
            logger.info(f"aria2c connected: {version}")
            return True
        except Exception as e:
            logger.error(f"aria2c connection failed: {e}")
            return False
    
    def download_magnet(self, magnet: str, chat_id: int, 
                     message_id: int, user_id: int) -> Optional[str]:
        """Add magnet link to download queue."""
        try:
            # Validate magnet link
            if not magnet.startswith("magnet:?"):
                raise InvalidURLError("Invalid magnet link format")
            
            # Parse magnet for basic info
            info = self._parse_magnet(magnet)
            title = info.get('name', 'Unknown torrent')
            
            # Add to aria2c
            gid = self.aria.add_magnet(
                magnet,
                dir=f"/downloads/torrents/{chat_id}",
                options={
                    'max-connection-per-server': 16,
                    'split': 16,
                    'split-every-mb': 10,
                    'continue': 'true',
                }
            )
            
            logger.info(f"Added torrent {gid}: {title}")
            
            # Store in database
            self.db.add_download(
                gid=gid,
                source_url=magnet,
                source_type='torrent',
                chat_id=chat_id,
                message_id=message_id
            )
            
            return gid
            
        except Exception as e:
            logger.error(f"Failed to add magnet: {e}")
            raise DownloadError(f"Could not add torrent: {str(e)}")
    
    def _parse_magnet(self, magnet: str) -> Dict:
        """Parse basic info from magnet link."""
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(magnet)
            params = urllib.parse.parse_qs(parsed.query)
            
            xt = params.get('xt', [''])[0]
            name = params.get('dn', ['Unknown'])[0]
            tr = params.get('tr', [])
            
            return {
                'name': name,
                'xt': xt,
                'trackers': tr,
                'size': 0  # Unknown from magnet alone
            }
        except Exception:
            return {'name': 'Unknown torrent', 'xt': '', 'trackers': []}
    
    def get_status(self, gid: str) -> Dict:
        """Get download status for a specific GID."""
        try:
            status = self.aria.tell_status(gid)
            
            return {
                'status': status.state,
                'progress': status.progress,
                'downloaded': status.completed_length,
                'total_size': status.total_length,
                'download_speed': status.download_speed,
                'eta': status.eta,
                'gid': gid
            }
        except Exception as e:
            logger.error(f"Failed to get status for {gid}: {e}")
            return {
                'status': 'error',
                'progress': 0,
                'downloaded': 0,
                'total_size': 0,
                'download_speed': 0,
                'eta': 0,
                'gid': gid
            }
    
    def pause_download(self, gid: str) -> bool:
        """Pause a download."""
        try:
            self.aria.pause(gid)
            logger.info(f"Paused download {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause {gid}: {e}")
            return False
    
    def remove_download(self, gid: str, force: bool = False) -> bool:
        """Remove download from queue."""
        try:
            self.aria.remove([gid], force=force)
            logger.info(f"Removed download {gid}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove {gid}: {e}")
            return False
    
    async def monitor_downloads(self, callback: Optional[Callable] = None):
        """Background task to monitor all active downloads."""
        logger.info("Starting download monitor...")
        
        while True:
            try:
                # Get all downloads from aria2c
                globals = self.aria.get_global_stat()
                active = self.aria.tell_active()
                
                for dl in active:
                    gid = dl.gid
                    status = self.get_status(gid)
                    
                    # Update database
                    progress = int(status['progress'] * 100)
                    self.db.update_download_progress(
                        gid=gid,
                        progress=progress,
                        downloaded=int(status['downloaded']),
                        speed=int(status['download_speed']),
                        eta=int(status.get('eta', 0)) if status['eta'] else 0
                    )
                    
                    # Check if completed
                    if status['status'] == 'complete':
                        file_path = dl.files[0].path if dl.files else None
                        logger.info(f"Download completed: {file_path}")
                        
                        # Mark complete in DB
                        # (Will be uploaded by separate process)
                    
                    # Callback for real-time updates
                    if callback:
                        await callback(status)
                
                await asyncio.sleep(5)  # Poll every 5 seconds
                
            except asyncio.CancelledError:
                logger.info("Download monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(10)  # Wait before retry
```

### 2. aria2c Installation & Setup

```bash
# Install aria2c
apt update
apt install -y aria2

# Start aria2c RPC server
aria2c --enable-rpc --rpc-listen-port=6800 --rpc-allow-public=true

# Verify it's running
curl http://localhost:6800/jsonrpc

# Or run in background
aria2c --enable-rpc --rpc-listen-port=6800 --rpc-allow-public=true &
```

### 3. Integration with Bot

```python
# In bot.py
from torrent_manager import TorrentManager

# Initialize
torrent_manager = TorrentManager(db=db)

# Start aria2c RPC
if not torrent_manager.check_connection():
    logger.error("aria2c RPC not available")
    # Option: auto-start aria2c or show error

# Add command handler
async def handle_torrent(update: Update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    
    # Get magnet link
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /torrent <magnet_link>")
        return
    
    magnet = args[0]
    
    try:
        # Validate
        if not magnet.startswith("magnet:?"):
            await update.message.reply_text("❌ Invalid magnet link")
            return
        
        # Add to queue
        gid = torrent_manager.download_magnet(magnet, chat_id, message_id, user_id)
        
        # Initial status
        status = torrent_manager.get_status(gid)
        
        response = f"""
📥 **Torrent Added!**

**GID:** {gid}
**Status:** {status['status']}
**Progress:** 0%

I'll download in background. Use /status to check progress.
        """
        
        await update.message.reply_text(response)
        db.log_activity(user_id, chat_id, 'torrent_added', {'gid': gid, 'magnet': magnet[:50]})
    
    except InvalidURLError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except DownloadError as e:
        await update.message.reply_text(f"❌ Download failed: {str(e)}")
```

### 4. Progress Tracking

```python
# Background task for real-time progress updates

async def start_progress_monitor():
    """Start background monitoring of all downloads."""
    logger.info("Starting progress monitor...")
    
    last_progress = {}
    
    while True:
        try:
            # Get all active downloads from DB
            # (This would need a new DB method to get all active downloads)
            
            for dl in active_downloads:
                gid = dl['gid']
                status = torrent_manager.get_status(gid)
                
                # Check if progress changed significantly
                last_p = last_progress.get(gid, 0)
                current_p = int(status['progress'] * 100)
                
                if abs(current_p - last_p) >= 5:  # Only update if 5%+ change
                    last_progress[gid] = current_p
                    
                    # Update progress message
                    await update_progress_message(dl, status)
            
            await asyncio.sleep(10)  # Check every 10 seconds
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Progress monitor error: {e}")
            await asyncio.sleep(30)
```

## Configuration

```python
# aria2c options
ARIA2C_OPTIONS = {
    'dir': '/downloads/torrents',
    'max-concurrent-downloads': 3,
    'max-connection-per-server': 16,
    'split': 16,
    'split-every-mb': 10,
    'continue': 'true',
    'max-overall-upload-limit': '0',  # No upload limit
    'max-overall-download-limit': '0',  # No download limit
}

# RPC configuration
RPC_URL = 'http://localhost:6800/jsonrpc'
RPC_SECRET = ''  # Add if using --rpc-secret
```

## Implementation Tasks

- [ ] Install aria2c on server
- [ ] Create `torrent_manager.py` with TorrentManager class
- [ ] Implement magnet link parsing
- [ ] Add to download queue (aria2c RPC)
- [ ] Implement progress polling (5-10 second intervals)
- [ ] Update database with progress
- [ ] Add pause/resume/remove commands
- [ ] Error handling (connection failures, invalid magnets)
- [ ] Test with sample magnet links
- [ ] Add concurrent download limits

## Dependencies

```python
# requirements.txt additions
aria2p>=1.0.0
```

## Notes

- **RPC Server:** aria2c must be running with --enable-rpc
- **Polling:** aria2p doesn't support WebSocket, so we poll
- **Progress:** Database updates every 5-10 seconds
- **File Paths:** Organize by chat_id: `/downloads/torrents/{chat_id}/`
- **Concurrent Downloads:** Limit to 3-5 at a time (bandwidth management)
