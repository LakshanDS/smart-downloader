"""
New URLs Handler - Smart Downloader

Multi-link submission with smart Done button routing.
Handles magnet links, direct URLs, yt-dlp, and crawler detection.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, link_submission_mode
from shared.auth import require_auth
from download.url_detector import get_url_detector

logger = logging.getLogger(__name__)

# Maximum links per submission session
MAX_LINKS = 30


def get_source_display(url_type: str) -> tuple[str, str]:
    """Map URL detector type to display name and DB source value."""
    mapping = {
        'torrent': ('Torrent', 'torrent'),
        'direct': ('Direct Download', 'direct'),
        'ytdlp': ('Direct Download', 'ytdlp'),
        'playwright': ('Direct Download', 'playwright'),
        'unknown': ('Direct Download', 'direct'),
    }
    return mapping.get(url_type, ('Direct Download', 'direct'))


@require_auth
async def show_new_url_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the new URL submission prompt."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    # Initialize submission mode
    link_submission_mode[chat_id] = {'active': True, 'count': 0}
    logger.info(f"Activated new URL submission mode for chat_id={chat_id}")

    from config import UPLOADER_API_ID, UPLOADER_API_HASH, UPLOADER_PHONE
    has_userbot = all([UPLOADER_API_ID, UPLOADER_API_HASH, UPLOADER_PHONE])

    if has_userbot:
        file_limit = "2GB"
        limit_note = "✅ Userbot configured!"
    else:
        file_limit = "50MB"
        limit_note = "⚠️ Standard bot limit - Setup userbot for 2GB support: /userbot_setup"

    keyboard = [[InlineKeyboardButton("✅ Done (0)", callback_data='newurl_done')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔗 *Send me download links...*\n\n"
        f"• *Magnet links* - for torrents\n"
        f"• *Direct URLs* - for videos, files, etc.\n\n"
        f"📁 File limit: {file_limit}\n"
        f"{limit_note}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


@require_auth
async def handle_new_url_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Done button - route to download manager or dashboard based on queue."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    # Exit submission mode
    if chat_id in link_submission_mode:
        del link_submission_mode[chat_id]
        logger.info(f"Exited new URL submission mode for chat_id={chat_id}")

    # Check if there are items in queue
    queue_summary = db.get_queue_summary()
    has_items = queue_summary['pending'] > 0 or queue_summary['downloading'] > 0

    if has_items:
        # Route to download manager
        from handlers.downloads import show_download_manager
        await show_download_manager(update, context, db)
    else:
        # Route to main dashboard
        from handlers.dashboard import show_main_dashboard
        await show_main_dashboard(update, context, query)


async def handle_url_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle URL submission when in new URL mode."""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # Check if in new URL submission mode
    if chat_id not in link_submission_mode or not link_submission_mode[chat_id].get('active'):
        logger.debug(f"URL submission ignored: not in new URL mode for chat_id={chat_id}")
        return

    logger.debug(f"New URL submission received: chat_id={chat_id}, text='{text[:50]}...'")

    # Check limit
    count = link_submission_mode[chat_id].get('count', 0)
    if count >= MAX_LINKS:
        await update.message.reply_text(
            f"⚠️ *Maximum {MAX_LINKS} links reached*\n\n"
            f"Click Done to continue.",
            parse_mode='Markdown'
        )
        return

    # Detect URL type
    detector = get_url_detector()
    url_type = detector.detect_url_type(text)

    if url_type == 'unknown':
        await update.message.reply_text(
            "❌ *Invalid link format*\n\n"
            "Please send:\n"
            "• Magnet links (torrents)\n"
            "• Direct URLs (videos, files, etc.)",
            parse_mode='Markdown'
        )
        return

    try:
        # Get display name and source value
        display_name, source_value = get_source_display(url_type)

        # Add to database
        logger.info(f"Adding to queue: url='{text[:50]}...', source={source_value}, chat_id={chat_id}")
        queue_id = db.add_to_queue(
            url=text,
            source=source_value,
            chat_id=chat_id,
            message_id=update.message.message_id
        )
        logger.info(f"Added to queue: queue_id={queue_id}")

        # Update count
        link_submission_mode[chat_id]['count'] = count + 1
        new_count = link_submission_mode[chat_id]['count']

        # Get queue position
        position, total = db.get_queue_position(queue_id)

        # Log activity
        db.log_activity(
            update.effective_user.id,
            chat_id,
            'link_queued',
            {'url': text[:50], 'source': source_value, 'queue_id': queue_id}
        )

        # Delete user's URL message
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete user message: {e}")

        # Send confirmation with updated Done button
        keyboard = [[InlineKeyboardButton(f"✅ Done ({new_count})", callback_data='newurl_done')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ *{display_name} added to queue!*\n\n"
            f"Position in queue: {position}\n"
            f"Send more links or click Done.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"URL queue error: {e}")
        await update.message.reply_text(f"❌ Failed to add to queue: {str(e)}")
