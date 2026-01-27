# Phase 5: Userbot Uploader Integration

**Objective:** Connect the main bot with a userbot account to enable 2 GB file uploads to Telegram.

## Architecture

```
@MediaServerBot (Main)
       │
       │ Has: File > 50 MB to send
       │
       │ "Upload this to @uploader_bot"
       ↓
┌────────────────────────────────────────┐
│  Telethon Userbot Client            │
│  - User API (2 GB limit)         │
│  - Separate phone/account           │
│  - Send file to 'Saved Messages'  │
└────────────────────────────────────────┘
       │
       │ Receives file
       │ Waits for upload completion
       │ Gets message.file_id
       ↓
       ┌─────────────────────────────────┐
       │  Update Main Bot Database    │
       │  - Store file_id             │
       │  - Mark upload complete        │
       └─────────────────────────────────┘
       │
       ↓
@MediaServerBot
       │
       │ forwards file_id to user
       ↓
    User can play any size file!
```

## Core Components

### 1. Userbot Client (`uploader_bot.py`)

```python
from telethon.sync import TelegramClient, events
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

class UploaderBot:
    """Userbot client for large file uploads."""
    
    def __init__(self, api_id: int, api_hash: str, phone: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.client = None
        self._connect()
    
    def _connect(self):
        """Initialize Telegram client connection."""
        try:
            self.client = TelegramClient(
                'uploader_bot',
                api_id=self.api_id,
                api_hash=self.api_hash,
                phone=self.phone
            )
            logger.info(f"Connecting userbot: {self.phone}")
            
            # Start client (synchronous for simplicity)
            self.client.connect()
            
            if not self.client.is_user_authorized():
                logger.info("Requesting auth code...")
                self.client.send_code_request(self.phone)
                logger.info("Check your Telegram for the code.")
                return False
            
            logger.info("Userbot connected and authorized!")
            return True
            
        except Exception as e:
            logger.error(f"Userbot connection failed: {e}")
            raise RuntimeError(f"Could not connect userbot: {str(e)}")
    
    def upload_file(self, file_path: str, caption: Optional[str] = None) -> Optional[Dict]:
        """Upload file to 'Saved Messages' (Telegram's cloud storage)."""
        try:
            logger.info(f"Uploading: {file_path}")
            
            # Upload file (supports up to 2 GB)
            message = self.client.send_file(
                'me',  # Upload to own chat
                file_path,
                caption=caption
            )
            
            logger.info(f"Upload complete: {message.id}")
            
            # Return file metadata
            return {
                'message_id': message.id,
                'file_id': message.video.file_id if hasattr(message, 'video') else message.document.file_id,
                'file_size': message.video.file_size if hasattr(message, 'video') else message.document.file_size,
                'file_name': message.video.file_name if hasattr(message, 'video') else message.document.file_name,
                'duration': message.video.duration if hasattr(message, 'video') else None
            }
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Could not upload file: {str(e)}")
    
    def disconnect(self):
        """Close userbot connection."""
        if self.client:
            self.client.disconnect()
            logger.info("Userbot disconnected")
```

### 2. Upload Manager (`upload_manager.py`)

```python
from uploader_bot import UploaderBot
from typing import Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

class UploadManager:
    """Manage file uploads via userbot."""
    
    def __init__(self, api_id: int, api_hash: str, phone: str):
        self.uploader = UploaderBot(api_id, api_hash, phone)
        self.queue: list = []
        self.uploading: bool = False
    
    def queue_upload(self, file_path: str, media_id: int) -> bool:
        """Add file to upload queue."""
        self.queue.append({
            'file_path': file_path,
            'media_id': media_id
        })
        logger.info(f"Queued upload: {file_path}")
        return True
    
    async def process_queue(self):
        """Process all queued uploads sequentially."""
        if self.uploading or not self.queue:
            return
        
        self.uploading = True
        
        while self.queue:
            item = self.queue.pop(0)
            
            try:
                # Upload to userbot
                result = self.uploader.upload_file(item['file_path'])
                
                # Update database with file_id
                # (This calls db.update_media_file_id)
                
                logger.info(f"Upload complete: {item['file_path']}")
                
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                # Mark as failed in DB
                # (This calls db.update_media_status)
            
            # Small delay between uploads
            await asyncio.sleep(1)
        
        self.uploading = False
        logger.info("Upload queue processed")
    
    def get_status(self) -> Dict:
        """Get current upload status."""
        return {
            'queue_size': len(self.queue),
            'uploading': self.uploading
        }
```

### 3. Integration with Main Bot

```python
# In bot.py
from upload_manager import UploadManager

# Initialize from config
UPLOADER_API_ID = int(os.getenv('UPLOADER_API_ID'))
UPLOADER_API_HASH = os.getenv('UPLOADER_API_HASH')
UPLOADER_PHONE = os.getenv('UPLOADER_PHONE')

# Create upload manager
upload_manager = UploadManager(
    api_id=UPLOADER_API_ID,
    api_hash=UPLOADER_API_HASH,
    phone=UPLOADER_PHONE
)

# Start upload processor in background
async def start_upload_processor():
    """Background task to process upload queue."""
    while True:
        await upload_manager.process_queue()
        await asyncio.sleep(5)  # Check every 5 seconds

# Add to bot startup
async def main():
    # ... existing bot setup ...
    
    # Start upload processor as background task
    asyncio.create_task(start_upload_processor())
    
    # Start bot
    app.run_polling()

# When download completes, queue for upload
def on_download_complete(file_path: str, media_id: int):
    """Called when a download finishes."""
    upload_manager.queue_upload(file_path, media_id)
```

## Configuration

```python
# config.py or environment variables
UPLOADER_API_ID = os.getenv('UPLOADER_API_ID')
UPLOADER_API_HASH = os.getenv('UPLOADER_API_HASH')
UPLOADER_PHONE = os.getenv('UPLOADER_PHONE')

# Or from a separate config file
import json

with open('uploader_config.json') as f:
    config = json.load(f)
    UPLOADER_API_ID = config['api_id']
    UPLOADER_API_HASH = config['api_hash']
    UPLOADER_PHONE = config['phone']
```

## Getting Userbot Credentials

```bash
# Step 1: Go to https://my.telegram.org
# Step 2: Create a new app
# - App title: Smart Downloader Uploader
# - Platform: Desktop
# - Description: Bot for large file uploads

# Step 3: Get credentials
# You'll receive:
# - api_id (number)
# - api_hash (string)

# Step 4: Run the script
# When first started, it will request phone verification
# You'll receive a code on Telegram

# Step 5: Save credentials to .env
UPLOADER_API_ID=123456
UPLOADER_API_HASH=your_api_hash_here
UPLOADER_PHONE=+9477xxxxxxx
```

## Security Considerations

- **Separate Account:** Userbot should be different from your personal account
- **Permissions:** Userbot only needs `send_file` to 'me'
- **Storage:** Files go to 'Saved Messages' (your private Telegram cloud)
- **Access:** Only main bot can trigger uploads (userbot has no commands)

## Implementation Tasks

- [ ] Create `uploader_bot.py` with UploaderBot class
- [ ] Implement TelegramClient initialization and auth flow
- [ ] Create `upload_manager.py` for queue management
- [ ] Add file upload to 'Saved Messages'
- [ ] Extract file_id from uploaded message
- [ ] Update database with file_id after upload
- [ ] Integrate with main bot (call on download complete)
- [ ] Add upload status tracking (queue size, active uploads)
- [ ] Handle upload errors gracefully (retry logic)
- [ ] Test with files of various sizes (50 MB, 500 MB, 2 GB)
- [ ] Add upload progress reporting to user

## Dependencies

```python
# requirements.txt additions
Telethon>=1.34.0
```

## Notes

- **2 GB Limit:** Userbot uploads are limited to 2 GB
- **Saved Messages:** Files uploaded to 'me' go here, accessible across devices
- **Sequential Uploads:** Queue ensures uploads don't fail due to rate limits
- **No Commands:** Userbot has no command handlers (passive upload service)
- **Forwarding Works:** Once file_id is stored, main bot can forward any size
