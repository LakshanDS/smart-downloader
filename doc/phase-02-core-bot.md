# Phase 2: Core Bot Framework

**Objective:** Build the Telegram bot foundation that handles user commands and routes to appropriate handlers.

## Architecture

```
@MediaServerBot (Main)
       │
       │ Receives: /torrent, /download, /movie, /tv, /porn, /myfiles
       │
       ├─────────────────────────────────────────┐
       │  Command Router                         │
       │  - Parse user input                    │
       │  - Route to appropriate handler           │
       │  - Validate permissions                  │
       └─────────────────────────────────────────┘
       │
       ├──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
       ↓                  ↓                  ↓                  ↓
   Torrent          Direct            Category          Chat
   Handler          Handler            Manager           Manager
   (Phase 3)       (Phase 4)         (Phase 6)        (Phase 7)
```

## Core Components

### 1. Bot Initialization (`bot.py`)

```python
import logging
from telegram import Update, Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler
from telegram.ext.filters import Filters
from database import DatabaseManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
db = DatabaseManager('smart_downloader.db')

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')  # From env or config
bot = Bot(token=BOT_TOKEN)
```

### 2. Command Router

```python
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

def main():
    """Run the bot."""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("torrent", handle_torrent))
    app.add_handler(CommandHandler("download", handle_download))
    app.add_handler(CommandHandler("movie", handle_browse_category))
    app.add_handler(CommandHandler("tv", handle_browse_category))
    app.add_handler(CommandHandler("porn", handle_browse_category))
    app.add_handler(CommandHandler("myfiles", handle_my_files))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("clear24h", handle_auto_clear))
    
    # Register callback handler (inline buttons)
    app.add_handler(CallbackQueryHandler(handle_button_press))
    
    # Start the bot
    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
```

### 3. Command Handlers

```python
# Basic commands

async def handle_start(update: Update, context):
    """Handle /start command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Log activity
    db.log_activity(user_id, chat_id, 'bot_start')
    
    # Create user preference if not exists
    if not db.get_user_preference(user_id):
        db.create_user_preference(user_id, chat_id)
    
    # Update chat activity
    db.update_chat_activity(chat_id)
    
    welcome_msg = """
🎬 Welcome to Smart Downloader!

Your personal media server using Telegram as storage.

**Commands:**
/torrent <magnet> - Download from magnet link
/download <url>   - Download direct link
/movie             - Browse your movies
/tv                - Browse TV shows
/porn              - Browse adult content
/myfiles           - Your full library
/status             - Active downloads
/clear24h <on/off> - Toggle auto-clear

💡 Send a magnet or direct URL to get started!
    """
    
    await update.message.reply_text(welcome_msg)


async def handle_help(update: Update, context):
    """Handle /help command."""
    help_text = """
📥 **Smart Downloader Help**

**Download Commands:**
`/torrent <magnet>` - Add torrent to queue
`/download <url>`   - Download direct HTTP/HTTPS link

**Browse Commands:**
`/movie` - View your movie library
`/tv`    - View your TV shows
`/porn`  - View adult content
`/myfiles` - View all files

**Management:**
`/status`  - Check active downloads
`/clear24h on/off` - Toggle 24h auto-clear

**Examples:`
/torrent magnet:?xt=urn:btih:...
/download https://example.com/video.mp4
    """
    
    await update.message.reply_text(help_text)


async def handle_status(update: Update, context):
    """Show active download status."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    db.update_chat_activity(chat_id)
    
    downloads = db.get_active_downloads(chat_id)
    
    if not downloads:
        await update.message.reply_text("✅ No active downloads")
        return
    
    status_msg = "📥 **Active Downloads:**\n\n"
    
    for i, dl in enumerate(downloads, 1):
        progress = dl['progress']
        speed = format_bytes(dl['download_speed'])
        eta = format_time(dl['eta_seconds']) if dl['eta_seconds'] else "Calculating..."
        
        progress_bar = create_progress_bar(progress)
        
        status_msg += f"{i}. {dl['source_url'][:50]}...\n"
        status_msg += f"   {progress_bar} {progress}%\n"
        status_msg += f"   ⚡ {speed}/s • ETA: {eta}\n\n"
    
    await update.message.reply_text(status_msg, parse_mode='Markdown')
```

### 4. Input Validation

```python
import re
from urllib.parse import urlparse

def validate_magnet_link(url: str) -> bool:
    """Check if URL is a valid magnet link."""
    return url.startswith('magnet:?')

def validate_direct_url(url: str) -> bool:
    """Check if URL is a valid HTTP/HTTPS URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
        return result.scheme in ('http', 'https')
    except:
        return False

def validate_category(category: str) -> bool:
    """Check if category exists."""
    valid_categories = ['movie', 'tv', 'porn', 'custom']
    return category.lower() in valid_categories
```

### 5. Utility Functions

```python
def format_bytes(bytes_per_sec: int) -> str:
    """Format bytes per second to human readable."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"

def format_time(seconds: int) -> str:
    """Format seconds to human readable time."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"

def create_progress_bar(progress: int, width: int = 20) -> str:
    """Create ASCII progress bar."""
    filled = int(width * progress / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}]"
```

## Error Handling

```python
class DownloadError(Exception):
    """Base exception for download-related errors."""
    pass

class InvalidURLError(DownloadError):
    """Raised when URL is invalid."""
    pass

class StorageLimitError(DownloadError):
    """Raised when storage limit exceeded."""
    pass

async def error_handler(update: Update, context):
    """Global error handler."""
    logger.error(f"Error: {context.error}", exc_info=context.error)
    
    await update.message.reply_text(
        "❌ Something went wrong. Please try again."
    )

# Register error handler
app.add_error_handler(error_handler)
```

## Configuration

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'smart_downloader.db')
UPLOADER_BOT_USERNAME = os.getenv('UPLOADER_BOT_USERNAME', 'uploader_bot')
MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '3'))
AUTO_CLEAR_DEFAULT_HOURS = int(os.getenv('AUTO_CLEAR_DEFAULT_HOURS', '24'))
```

## Implementation Tasks

- [ ] Set up project structure
- [ ] Create bot.py with command router
- [ ] Implement basic commands (start, help, status)
- [ ] Add input validation for URLs
- [ ] Integrate DatabaseManager
- [ ] Set up logging configuration
- [ ] Add error handlers
- [ ] Test bot startup and command routing
- [ ] Configure environment variables

## Dependencies

```python
# requirements.txt additions
python-telegram-bot>=20.0
python-dotenv>=1.0.0
```

## Notes

- **Async architecture:** Telegram bot uses async/await
- **Separation of concerns:** Each handler is focused
- **Database integration:** All handlers use DatabaseManager
- **Extensible:** Easy to add new commands
- **Error handling:** Graceful degradation on failures
