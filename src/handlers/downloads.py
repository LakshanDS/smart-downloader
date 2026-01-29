"""Download command handlers - /download, /torrent, /status, /help, link submission."""

import logging
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, link_submission_mode, userbot_setup
import shared.state as state
from shared.auth import check_authorized, InvalidURLError

logger = logging.getLogger(__name__)


async def handle_non_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages from non-owners."""
    await update.message.reply_text(
        "❌ This bot is locked to another account.\n"
        "You cannot use it."
    )


def detect_source_type(url: str) -> str:
    """Detect download source type from URL."""
    if url.startswith('magnet:?'):
        return 'torrent'
    elif url.startswith(('http://', 'https://')):
        return 'direct'
    else:
        raise InvalidURLError("Unknown URL format")


async def handle_link_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle link submission when in new download mode."""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # Skip if userbot setup is active (let userbot handler handle it)
    if chat_id in userbot_setup:
        logger.debug(f"Link submission skipped: userbot setup is active for chat_id={chat_id}")
        return

    logger.debug(f"Link submission received: chat_id={chat_id}, text='{text[:50]}...', mode_active={chat_id in link_submission_mode}")

    if chat_id not in link_submission_mode or not link_submission_mode[chat_id].get('active'):
        logger.debug(f"Link submission ignored: not in submission mode")
        return

    if text.startswith('magnet:?'):
        source = 'torrent'
        display_name = "Torrent"
    elif text.startswith(('http://', 'https://')):
        source = 'direct'
        display_name = "Direct Download"
    else:
        await update.message.reply_text(
            "❌ *Invalid link format*\n\n"
            "Please send:\n"
            "• Magnet links (torrents)\n"
            "• Direct URLs (videos, files, etc.)",
            parse_mode='Markdown'
        )
        return

    try:
        logger.debug(f"state.queue_manager check: {state.queue_manager}, type: {type(state.queue_manager)}")
        if state.queue_manager is None:
            logger.error("Queue manager is None! Cannot add link to queue.")
            await update.message.reply_text("⚠️ Queue manager not initialized. Please restart the bot.")
            return

        logger.info(f"Adding to queue: url='{text[:50]}...', source={source}, chat_id={chat_id}")
        queue_id = await state.queue_manager.add_to_queue(
            url=text,
            source=source,
            chat_id=chat_id
        )
        logger.info(f"Added to queue: queue_id={queue_id}")

        queue_summary = db.get_queue_summary()

        keyboard = [[InlineKeyboardButton("✅ Done", callback_data='dashboard_new_download_done')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *{display_name} added to queue!*\n\n"
            f"Position in queue: {queue_summary['pending']}\n\n"
            f"Send more links or click *Done*.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        db.log_activity(
            update.effective_user.id,
            chat_id,
            'link_queued',
            {'url': text[:50], 'source': source, 'queue_id': queue_id}
        )

    except Exception as e:
        logger.error(f"Link queue error: {e}")
        await update.message.reply_text(f"❌ Failed to add to queue: {str(e)}")


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

    progress = active['progress']
    dl_speed = active.get('download_speed', 0) or 0
    ul_speed = active.get('upload_speed', 0) or 0
    eta = active.get('eta_seconds', 0) or 0

    filled = int(20 * progress / 100)
    bar = '█' * filled + '░' * (20 - filled)

    dl_str = f"{dl_speed:.2f} MB/s" if dl_speed else "0.00 MB/s"
    ul_str = f"{ul_speed:.2f} MB/s" if ul_speed else "0.00 MB/s"

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

    if len(url) > 2048:
        await update.message.reply_text("❌ URL too long (max 2048 characters)")
        return

    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL format")
    except ValueError as e:
        await update.message.reply_text(f"❌ Invalid URL: {str(e)}")
        return

    try:
        source = detect_source_type(url)

        await update.message.delete()

        if state.queue_manager is None:
            await update.message.reply_text(
                "⚠️ Queue manager not initialized. Please restart the bot."
            )
            return

        queue_id = await state.queue_manager.add_to_queue(
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
        await update.message.delete()

        if state.queue_manager is None:
            await update.message.reply_text(
                "⚠️ Queue manager not initialized. Please restart the bot."
            )
            return

        queue_id = await state.queue_manager.add_to_queue(
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


async def handle_loglevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change log level dynamically: /loglevel <DEBUG|INFO|WARNING|ERROR>"""
    if not check_authorized(update.effective_chat.id):
        await handle_non_owner(update, context)
        return

    import logging
    from pathlib import Path

    valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR'}

    if not context.args:
        current_level = logging.getLogger().getEffectiveLevel()
        level_name = logging.getLevelName(current_level)
        await update.message.reply_text(
            f"📊 Current log level: *{level_name}*\n\n"
            f"Usage: `/loglevel <level>`\n"
            f"Valid levels: {', '.join(valid_levels)}",
            parse_mode='Markdown'
        )
        return

    requested_level = context.args[0].upper()

    if requested_level not in valid_levels:
        await update.message.reply_text(
            f"❌ Invalid level. Use: {', '.join(valid_levels)}"
        )
        return

    new_level = getattr(logging, requested_level)

    # Update all handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(new_level)
    for handler in root_logger.handlers:
        handler.setLevel(new_level)

    # Also update .env file for persistence
    env_path = Path(__file__).parent.parent.parent / ".env"
    try:
        with open(env_path, 'r') as f:
            lines = f.readlines()
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('LOG_LEVEL='):
                    f.write(f'LOG_LEVEL={requested_level}\n')
                else:
                    f.write(line)
    except Exception as e:
        logger.warning(f"Could not update .env file: {e}")

    await update.message.reply_text(
        f"✅ Log level changed to: *{requested_level}*\n\n"
        f"Restart bot to apply to .env file (current session already updated).",
        parse_mode='Markdown'
    )
    logger.info(f"Log level changed to {requested_level} by user {update.effective_user.id}")
