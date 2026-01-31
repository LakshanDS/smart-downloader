"""
Core Bot Framework - Smart Downloader

Route registration only. All handlers moved to handlers/ package.
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from config import BOT_TOKEN, LOG_LEVEL, DATABASE_PATH
from shared.state import db

# Import handlers
from handlers import (
    handle_start,
    handle_setup,
    handle_setup_callback,
    handle_verify_code,
    handle_dashboard_callback,
    handle_queue_callback,
    handle_userbot_setup,
    handle_userbot_setup_callback,
    handle_userbot_setup_text,
    handle_userbot_confirm,
    handle_help_command,
    handle_help_callback,
    handle_status,
    handle_url_submission,
    handle_new_url_done,
    handle_start_downloads,
    handle_stop_downloads,
    handle_restart_downloads,
    handle_downloads_status,
)

# Setup logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Configure logging with file and console handlers
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_level = getattr(logging, LOG_LEVEL)

# File handler with rotation
file_handler = RotatingFileHandler(
    LOGS_DIR / "bot.log",
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(log_format))
file_handler.setLevel(log_level)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(log_format))
console_handler.setLevel(log_level)

# Root logger configuration
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Suppress noisy third-party logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('telethon').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)
logging.getLogger('telegram.ext.ExtBot').setLevel(logging.WARNING)
logging.getLogger('telegram.ext.Updater').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler."""
    logger.error(f"Error: {context.error}", exc_info=context.error)

    if update and hasattr(update, 'effective_message'):
        try:
            await update.effective_message.reply_text(
                "❌ Something went wrong. Please try again."
            )
        except Exception:
            pass


async def startup_pooler(app: Application):
    """Initialize download process on startup if bot is already set up."""
    import shared.state as state

    print("✓ Bot application initialized", file=sys.stderr)

    if db.is_locked():
        print("✓ Bot is set up. Starting download process...", file=sys.stderr)
        logger.info("Bot is set up. Starting download process...")
        try:
            from src.pooler import start_download_process

            # Start download process
            success = start_download_process(db_path=DATABASE_PATH)

            if success:
                status = state.pooler.get_status() if hasattr(state, 'pooler') else None
                pid = status.get('pid') if status else None
                logger.info(f"Download process started (PID: {pid})")
                print(f"✓ Download process started (PID: {pid})", file=sys.stderr)
            else:
                print(f"⚠ Failed to start download process", file=sys.stderr)
                logger.warning("Failed to start download process")

        except Exception as e:
            print(f"⚠ Failed to start download process: {e}", file=sys.stderr)
            logger.error(f"Failed to start download process: {e}", exc_info=True)
    else:
        print("⚠ Bot not set up. Waiting for /setup command...", file=sys.stderr)
        logger.info("Bot not set up. Waiting for /setup command...")

    print("✓ Bot started successfully. Polling for messages...", file=sys.stderr)


async def shutdown_pooler(app: Application):
    """Shutdown download process on bot shutdown."""
    import shared.state as state

    print("Shutting down download process...", file=sys.stderr)
    logger.info("Shutting down download process...")

    try:
        from src.pooler import stop_download_process
        stop_download_process(timeout=30)
        print("✓ Download process stopped", file=sys.stderr)
        logger.info("Download process stopped")
    except Exception as e:
        print(f"⚠ Failed to stop download process: {e}", file=sys.stderr)
        logger.error(f"Failed to stop download process: {e}")

    db.close()


def create_application() -> Application:
    """Create and configure the bot application."""
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("setup", handle_setup))
    app.add_handler(CommandHandler("userbot_setup", handle_userbot_setup))
    app.add_handler(CommandHandler("help", handle_help_command))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("start_downloads", handle_start_downloads))
    app.add_handler(CommandHandler("stop_downloads", handle_stop_downloads))
    app.add_handler(CommandHandler("restart_downloads", handle_restart_downloads))
    app.add_handler(CommandHandler("downloads_status", handle_downloads_status))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_setup_callback, pattern='^setup_initiate$'))
    app.add_handler(CallbackQueryHandler(handle_queue_callback, pattern='^(dashboard_queue|queue_)'))
    app.add_handler(CallbackQueryHandler(handle_dashboard_callback, pattern='^dashboard_'))
    app.add_handler(CallbackQueryHandler(handle_dashboard_callback, pattern='^dm_'))
    app.add_handler(CallbackQueryHandler(handle_userbot_setup_callback, pattern='^userbot_cancel$'))
    app.add_handler(CallbackQueryHandler(handle_userbot_confirm, pattern='^userbot_confirm$'))
    app.add_handler(CallbackQueryHandler(handle_new_url_done, pattern='^newurl_done$'))
    app.add_handler(CallbackQueryHandler(handle_help_callback, pattern='^help_'))

    # Messages (order matters - most common first)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_submission))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_userbot_setup_text))
    app.add_handler(MessageHandler(filters.Regex(r'^\d{6}$'), handle_verify_code))

    app.add_error_handler(error_handler)

    return app


def main():
    """Run the bot."""
    print("=" * 50, file=sys.stderr)
    print("Smart Downloader Bot - Starting...", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    app = create_application()
    app.post_init = startup_pooler
    app.post_shutdown = shutdown_pooler

    logger.info("Starting bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
