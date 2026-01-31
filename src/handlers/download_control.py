"""
Download Process Control Handlers

Handlers for manual control of the download process:
- /start_downloads - Start download process
- /stop_downloads - Stop download process
- /restart_downloads - Restart download process
- /downloads_status - Show download process status
"""

from telegram import Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)


async def handle_start_downloads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start_downloads command - Start download process."""
    try:
        from src.pooler import start_download_process, get_download_status

        # Check if already running
        status = get_download_status()
        if status.get('running'):
            await update.message.reply_text(
                "⚠️ Download process is already running.\n\n"
                f"PID: {status.get('pid')}"
            )
            return

        # Start download process
        success = start_download_process()

        if success:
            status = get_download_status()
            await update.message.reply_text(
                "✅ Download process started successfully!\n\n"
                f"PID: {status.get('pid')}"
            )
            logger.info(f"Download process started by user {update.effective_user.id}")
        else:
            await update.message.reply_text(
                "❌ Failed to start download process.\n"
                "Check logs for details."
            )
            logger.warning(f"Failed to start download process by user {update.effective_user.id}")

    except Exception as e:
        logger.error(f"Error in handle_start_downloads: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {e}"
        )


async def handle_stop_downloads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop_downloads command - Stop download process."""
    try:
        from src.pooler import stop_download_process, get_download_status

        # Check if running
        status = get_download_status()
        if not status.get('running'):
            await update.message.reply_text(
                "⚠️ Download process is not running."
            )
            return

        # Stop download process
        success = stop_download_process(timeout=30)

        if success:
            await update.message.reply_text(
                "✅ Download process stopped successfully!\n\n"
                "Note: Current download will complete gracefully."
            )
            logger.info(f"Download process stopped by user {update.effective_user.id}")
        else:
            await update.message.reply_text(
                "❌ Failed to stop download process.\n"
                "Check logs for details."
            )
            logger.warning(f"Failed to stop download process by user {update.effective_user.id}")

    except Exception as e:
        logger.error(f"Error in handle_stop_downloads: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {e}"
        )


async def handle_restart_downloads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart_downloads command - Restart download process."""
    try:
        from src.pooler import restart_download_process, get_download_status

        # Restart download process
        success = restart_download_process(timeout=30)

        if success:
            status = get_download_status()
            await update.message.reply_text(
                "✅ Download process restarted successfully!\n\n"
                f"PID: {status.get('pid')}"
            )
            logger.info(f"Download process restarted by user {update.effective_user.id}")
        else:
            await update.message.reply_text(
                "❌ Failed to restart download process.\n"
                "Check logs for details."
            )
            logger.warning(f"Failed to restart download process by user {update.effective_user.id}")

    except Exception as e:
        logger.error(f"Error in handle_restart_downloads: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {e}"
        )


async def handle_downloads_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /downloads_status command - Show download process status."""
    try:
        from src.pooler import get_download_status

        status = get_download_status()

        # Build status message
        if status.get('running'):
            msg = (
                "📊 **Download Process Status**\n\n"
                f"Status: ✅ Running\n"
                f"PID: {status.get('pid')}\n"
            )
        else:
            msg = (
                "📊 **Download Process Status**\n\n"
                "Status: ⏹️ Stopped\n"
            )

        # Add queue info if available
        if 'queue' in status:
            queue = status['queue']
            msg += (
                "\n📦 **Queue:**\n"
                f"  • Pending: {queue.get('pending', 0)}\n"
                f"  • Downloading: {queue.get('downloading', 0)}\n"
                f"  • Uploading: {queue.get('uploading', 0)}\n"
                f"  • Failed: {queue.get('failed', 0)}\n"
            )

        await update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in handle_downloads_status: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {e}"
        )
