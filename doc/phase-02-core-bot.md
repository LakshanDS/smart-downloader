# Phase 2: Core Bot Framework

**Objective:** Build the Telegram bot foundation with owner lock, setup wizard, and queue-based command routing.

## Key Changes from Original Plan

- **Single-user focus**: Setup wizard locks bot to one chat ID
- **Queue-based routing**: All downloads go to queue, not direct handlers
- **Progress display**: Single summary message (edited every 5s)
- **Outsider rejection**: Non-owners are ignored

## Architecture

```
@MediaServerBot (Main)
       │
       │ First run? → Setup Wizard → Lock to owner
       │
       │ Commands: /start, /setup, /download, /torrent, /status, /search, /favorites, /myfiles
       │
       ├─────────────────────────────────────────┐
       │  Owner Lock Check                      │
       │  - Reject all non-owners               │
       └─────────────────────────────────────────┘
       │
       ├──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
       ↓                  ↓                  ↓                  ↓
   Queue          Search           Favorites         Status
   Manager         Handler           Handler           Display
   (Phase 3)      (Phase 8)         (Phase 8)        (Built-in)
```

## Core Components

### 1. Bot Initialization with Setup Wizard (`bot.py`)

```python
import logging
import os
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler
from telegram.ext.filters import Filters
from database import DatabaseManager
from queue_manager import QueueManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
db = DatabaseManager(os.getenv('DATABASE_PATH', 'smart_downloader.db'))

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Initialize queue manager (will be started after setup)
queue_manager = None

async def handle_start(update: Update, context):
    """Handle /start command."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username

    # Check if bot is locked
    if not db.is_locked():
        await update.message.reply_text(
            "🔐 **Setup Required**\n\n"
            "This bot needs to be locked to your account first.\n"
            "Use /setup to complete setup."
        )
        return

    # Check authorization
    if not db.is_authorized(chat_id):
        await update.message.reply_text(
            "❌ This bot is already locked to another account.\n"
            "You cannot use it."
        )
        return

    # Update chat activity
    db.log_activity(user_id, chat_id, 'bot_start')

    welcome_msg = """
🎬 **Smart Downloader**

Your personal media server using Telegram as storage.

**Commands:**
/download <url> - Download from direct link
/torrent <magnet> - Download torrent
/myfiles - Browse your library
/search <query> - Search your files
/favorites - View watch later
/status - Active downloads

💡 Send a link to get started!
    """

    await update.message.reply_text(welcome_msg)


async def handle_setup(update: Update, context):
    """Handle /setup command (one-time setup wizard)."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username

    # Check if already locked
    if db.is_locked():
        owner = db.get_owner()
        if owner['chat_id'] == chat_id:
            await update.message.reply_text(
                "✅ Bot is already set up and locked to your account!"
            )
        else:
            await update.message.reply_text(
                "❌ This bot is already locked to another account."
            )
        return

    # Lock to this user
    try:
        db.set_owner(chat_id, user_id, username)
        logger.info(f"Bot locked to user {username} (ID: {user_id})")

        await update.message.reply_text(
            f"✅ **Setup Complete!**\n\n"
            f"Bot locked to: @{username or 'N/A'}\n"
            f"User ID: {user_id}\n\n"
            f"Only you can use this bot now.\n"
            f"Use /start to see available commands."
        )

        # Start queue manager after setup
        global queue_manager
        queue_manager = QueueManager(db=db, bot=context.bot)
        asyncio.create_task(queue_manager.start())

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        await update.message.reply_text(f"❌ Setup failed: {str(e)}")


async def handle_help(update: Update, context):
    """Handle /help command."""
    if not db.is_authorized(update.effective_chat.id):
        return

    help_text = """
📥 **Smart Downloader Help**

**Download Commands:**
`/torrent <magnet>` - Add torrent to queue
`/download <url>` - Download direct link

**Browse Commands:**
`/myfiles` - View your library
`/search <query>` - Search files
`/favorites` - Watch later list

**Management:**
`/status` - Active downloads

**All downloads are processed sequentially, one at a time.**
    """

    await update.message.reply_text(help_text)


async def handle_status(update: Update, context):
    """Show active download status."""
    if not db.is_authorized(update.effective_chat.id):
        return

    active = db.get_active_download()
    queue_summary = db.get_queue_summary()

    if not active:
        if queue_summary['pending'] == 0:
            await update.message.reply_text("✅ No active downloads")
        else:
            await update.message.reply_text(
                f"⏳ {queue_summary['pending']} items in queue.\n"
                f"Starting next download shortly..."
            )
        return

    # Show current active download
    progress = active['progress']
    dl_speed = active.get('download_speed', 0) or 0
    ul_speed = active.get('upload_speed', 0) or 0
    eta = active.get('eta_seconds', 0) or 0

    # Progress bar
    filled = int(20 * progress / 100)
    bar = '█' * filled + '░' * (20 - filled)

    # Format speeds
    dl_str = f"{dl_speed:.2f} MB/s" if dl_speed else "0.00 MB/s"
    ul_str = f"{ul_speed:.2f} MB/s" if ul_speed else "0.00 MB/s"

    # Format ETA
    if eta > 0:
        eta_mins = eta // 60
        eta_secs = eta % 60
        eta_str = f"{eta_mins}m {eta_secs}s"
    else:
        eta_str = "Calculating..."

    status_text = "Downloading" if active['status'] == 'downloading' else "Uploading"

    message = f"""
📥 **Active Download:**

{status_text} 1/{queue_summary['pending'] + 1}:
📹 {active['title'] or 'Processing...'}
[{bar}] {progress}%
⏱️ ETA: {eta_str}
↓ {dl_str} | ↑ {ul_str}
    """

    await update.message.reply_text(message)
```

### 2. Download Command Handlers

```python
def detect_source_type(url: str) -> str:
    """Detect download source type from URL."""
    if url.startswith('magnet:?'):
        return 'torrent'
    elif url.startswith(('http://', 'https://')):
        # Check if yt-dlp supports it
        if is_ytdlp_supported(url):
            return 'direct'
        else:
            return 'crawler'
    else:
        raise ValueError("Unknown URL format")


def is_ytdlp_supported(url: str) -> bool:
    """Check if URL is supported by yt-dlp."""
    # Common yt-dlp supported sites
    supported_domains = [
        'youtube.com', 'youtu.be',
        'vimeo.com',
        'dailymotion.com',
        # Add more as needed
    ]

    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()

    return any(domain in supported_domains)


async def handle_download(update: Update, context):
    """Handle /download command."""
    if not db.is_authorized(update.effective_chat.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /download <url>")
        return

    url = args[0]

    try:
        # Detect source type
        source = detect_source_type(url)

        # Delete user's message
        await update.message.delete()

        # Add to queue
        queue_id = await queue_manager.add_to_queue(
            url=url,
            source=source,
            chat_id=update.effective_chat.id
        )

        queue_summary = db.get_queue_summary()

        await update.message.reply_text(
            f"✅ Added to queue!\n\n"
            f"Source: {source.title()}\n"
            f"Position in queue: {queue_summary['pending']}\n"
            f"I'll start processing shortly..."
        )

        db.log_activity(
            update.effective_user.id,
            update.effective_chat.id,
            'download_queued',
            {'url': url, 'source': source, 'queue_id': queue_id}
        )

    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Download queue error: {e}")
        await update.message.reply_text(f"❌ Failed to add to queue: {str(e)}")


async def handle_torrent(update: Update, context):
    """Handle /torrent command."""
    if not db.is_authorized(update.effective_chat.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /torrent <magnet_link>")
        return

    magnet = args[0]

    if not magnet.startswith('magnet:?'):
        await update.message.reply_text("❌ Invalid magnet link")
        return

    try:
        # Delete user's message
        await update.message.delete()

        # Add to queue
        queue_id = await queue_manager.add_to_queue(
            url=magnet,
            source='torrent',
            chat_id=update.effective_chat.id
        )

        queue_summary = db.get_queue_summary()

        await update.message.reply_text(
            f"✅ Torrent added to queue!\n\n"
            f"Position in queue: {queue_summary['pending']}"
        )

        db.log_activity(
            update.effective_user.id,
            update.effective_chat.id,
            'torrent_queued',
            {'magnet': magnet[:50], 'queue_id': queue_id}
        )

    except Exception as e:
        logger.error(f"Torrent queue error: {e}")
        await update.message.reply_text(f"❌ Failed to add torrent: {str(e)}")


# Prevent command handlers for non-owners
async def handle_non_owner(update: Update, context):
    """Handle messages from non-owners."""
    await update.message.reply_text(
        "❌ This bot is locked to another account.\n"
        "You cannot use it."
    )
```

### 3. Main Bot Application

```python
def main():
    """Run the bot."""
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("setup", handle_setup))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("download", handle_download))
    app.add_handler(CommandHandler("torrent", handle_torrent))
    app.add_handler(CommandHandler("status", handle_status))

    # Register handlers for Phase 8 (search, favorites, myfiles)
    # These will be added in Phase 8

    # Register error handler
    async def error_handler(update: Update, context):
        logger.error(f"Error: {context.error}", exc_info=context.error)

    app.add_error_handler(error_handler)

    # Check if setup is complete
    if not db.is_locked():
        logger.info("Bot not set up. Waiting for /setup command...")
    else:
        logger.info("Bot set up. Starting queue manager...")
        global queue_manager
        queue_manager = QueueManager(db=db)
        # Queue manager will be started after bot starts

    # Start the bot
    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    import asyncio
    # Note: Queue manager start will be handled in bot startup
    main()
```

## Configuration

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'smart_downloader.db')

# Userbot credentials (for Phase 7)
UPLOADER_API_ID = os.getenv('UPLOADER_API_ID')
UPLOADER_API_HASH = os.getenv('UPLOADER_API_HASH')
UPLOADER_PHONE = os.getenv('UPLOADER_PHONE')

# Download settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
PROGRESS_UPDATE_INTERVAL = 5  # seconds
RETRY_DELAYS = [0, 120, 480]  # 0s, 2min, 8min
```

## Environment Variables

```bash
# .env file
TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_PATH=smart_downloader.db

# Userbot credentials (Phase 7)
UPLOADER_API_ID=123456
UPLOADER_API_HASH=your_api_hash
UPLOADER_PHONE=+9477xxxxxxx
```

## Error Handling

```python
class BotError(Exception):
    """Base exception for bot errors."""
    pass

class NotAuthorizedError(BotError):
    """Raised when non-owner tries to use bot."""
    pass

class InvalidURLError(BotError):
    """Raised when URL is invalid."""
    pass

class FileTooLargeError(BotError):
    """Raised when file exceeds 2GB limit."""
    pass


async def error_handler(update: Update, context):
    """Global error handler."""
    logger.error(f"Error: {context.error}", exc_info=context.error)

    # Send user-friendly message
    if update.effective_message:
        await update.message.reply_text(
            "❌ Something went wrong. Please try again."
        )
```

## Implementation Tasks

- [ ] Set up project structure
- [ ] Create bot.py with command router
- [ ] Implement setup wizard (/setup command)
- [ ] Add owner lock checks to all commands
- [ ] Implement /start, /help, /status commands
- [ ] Add input validation for URLs
- [ ] Integrate QueueManager
- [ ] Set up logging configuration
- [ ] Add error handlers
- [ ] Test bot startup and command routing
- [ ] Test setup wizard flow
- [ ] Test owner lock enforcement
- [ ] Configure environment variables

## Dependencies

```python
# requirements.txt
python-telegram-bot>=21.0
python-dotenv>=1.0.0
# (database.py has no external deps)
# (queue_manager.py uses database.py)
```

## Setup Flow

```
1. User creates bot via @BotFather
2. User gets BOT_TOKEN
3. User sets .env file
4. User runs bot
5. User sends /setup command
6. Bot verifies and locks to user's chat_id
7. Bot is now ready for downloads
8. Non-owners are rejected
```

## Notes

- **Setup wizard**: One-time /setup command locks bot
- **Owner lock**: Cannot be changed once set
- **Queue-based**: All downloads go to queue manager
- **Progress display**: Single message edited every 5s
- **Non-owners**: All commands rejected
- **Error handling**: Graceful user-friendly messages
