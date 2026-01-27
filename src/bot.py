"""
Core Bot Framework - Smart Downloader

Phase 2: Core Bot Framework
Implements Telegram bot with owner lock, setup wizard, and command routing.
"""

import logging
import os
import asyncio
from typing import Optional
from urllib.parse import urlparse

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from database import DatabaseManager
from config import (
    DATABASE_PATH,
    LOG_LEVEL,
    MAX_FILE_SIZE,
    PROGRESS_UPDATE_INTERVAL,
    RETRY_DELAYS
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)


# Global instances
db = DatabaseManager(DATABASE_PATH)
queue_manager = None


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


def check_authorized(chat_id: int) -> bool:
    """Check if chat_id is authorized (owner)."""
    return db.is_authorized(chat_id)


# === Setup Wizard ===

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if not check_authorized(chat_id):
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

    await update.message.reply_text(welcome_msg, parse_mode='Markdown')


async def handle_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        from queue_manager import QueueManager
        queue_manager = QueueManager(db=db, bot=context.bot)
        asyncio.create_task(queue_manager.start())

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        await update.message.reply_text(f"❌ Setup failed: {str(e)}")


# === Help & Status ===

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    if not check_authorized(update.effective_chat.id):
        await handle_non_owner(update, context)
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

    await update.message.reply_text(help_text, parse_mode='Markdown')


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active download status."""
    if not check_authorized(update.effective_chat.id):
        await handle_non_owner(update, context)
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

    await update.message.reply_text(message, parse_mode='Markdown')


# === Download Commands ===

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
        raise InvalidURLError("Unknown URL format")


def is_ytdlp_supported(url: str) -> bool:
    """Check if URL is supported by yt-dlp."""
    # yt-dlp supports 1000+ sites, let it handle all HTTP/HTTPS URLs
    return url.startswith(('http://', 'https://'))


async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /download command."""
    if not check_authorized(update.effective_chat.id):
        await handle_non_owner(update, context)
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /download <url>")
        return

    url = args[0]

    # Validate URL length
    if len(url) > 2048:
        await update.message.reply_text("❌ URL too long (max 2048 characters)")
        return

    # Validate URL format
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL format")
    except ValueError as e:
        await update.message.reply_text(f"❌ Invalid URL: {str(e)}")
        return

    try:
        # Detect source type
        source = detect_source_type(url)

        # Delete user's message
        await update.message.delete()

        # Add to queue
        if queue_manager is None:
            await update.message.reply_text(
                "⚠️ Queue manager not initialized. Please restart the bot."
            )
            return

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

    except InvalidURLError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Download queue error: {e}")
        await update.message.reply_text(f"❌ Failed to add to queue: {str(e)}")


async def handle_torrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /torrent command."""
    if not check_authorized(update.effective_chat.id):
        await handle_non_owner(update, context)
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
        if queue_manager is None:
            await update.message.reply_text(
                "⚠️ Queue manager not initialized. Please restart the bot."
            )
            return

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


# === Non-Owner Handler ===

async def handle_non_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages from non-owners."""
    await update.message.reply_text(
        "❌ This bot is locked to another account.\n"
        "You cannot use it."
    )


# === Error Handler ===

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler."""
    logger.error(f"Error: {context.error}", exc_info=context.error)

    # Send user-friendly message
    if update and hasattr(update, 'effective_message'):
        try:
            await update.effective_message.reply_text(
                "❌ Something went wrong. Please try again."
            )
        except Exception:
            pass


# === Main Application ===

def create_application() -> Application:
    """Create and configure the bot application."""
    from config import BOT_TOKEN

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
    app.add_error_handler(error_handler)

    return app


async def startup_queue_manager(app: Application):
    """Initialize queue manager on startup if bot is already set up."""
    global queue_manager
    if db.is_locked():
        logger.info("Bot is set up. Initializing queue manager...")
        try:
            from queue_manager import QueueManager
            queue_manager = QueueManager(db=db, bot=app.bot)
            asyncio.create_task(queue_manager.start())
        except ImportError:
            logger.warning("QueueManager not implemented yet (coming in Phase 3)")
    else:
        logger.info("Bot not set up. Waiting for /setup command...")


def main():
    """Run the bot."""
    app = create_application()

    # Add startup handler
    app.post_init = startup_queue_manager

    # Start bot
    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
