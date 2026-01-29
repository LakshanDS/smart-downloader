"""Dashboard handlers - inline keyboard callbacks."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, link_submission_mode
from shared.auth import check_authorized

logger = logging.getLogger(__name__)


async def handle_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dashboard button callbacks."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    action = query.data

    logger.debug(f"[DASHBOARD] callback: {action} from chat_id={chat_id}")

    if not check_authorized(chat_id):
        await query.edit_message_text("❌ You are not authorized to use this bot.")
        return

    # Skip queue callbacks - handled by handle_queue_callback
    if action.startswith('dashboard_queue') or action.startswith('queue_'):
        logger.debug(f"[DASHBOARD] skipping queue callback: {action}")
        return

    if action == 'dashboard_new_download':
        link_submission_mode[chat_id] = {'active': True}
        logger.info(f"Activated link submission mode for chat_id={chat_id}")

        from config import UPLOADER_API_ID, UPLOADER_API_HASH, UPLOADER_PHONE
        has_userbot = all([UPLOADER_API_ID, UPLOADER_API_HASH, UPLOADER_PHONE])

        if has_userbot:
            file_limit = "2GB"
            limit_note = "✅ Userbot configured!"
        else:
            file_limit = "50MB"
            limit_note = "⚠️ Standard bot limit - Setup userbot for 2GB support: /userbot_setup"

        keyboard = [[InlineKeyboardButton("✅ Done", callback_data='dashboard_new_download_done')]]
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
        return

    if action == 'dashboard_new_download_done':
        if chat_id in link_submission_mode:
            del link_submission_mode[chat_id]
            logger.info(f"Deactivated link submission mode for chat_id={chat_id} (Done button)")

    if action == 'dashboard_back' or action == 'dashboard_new_download_done':
        if chat_id in link_submission_mode:
            del link_submission_mode[chat_id]

        keyboard = [
            [InlineKeyboardButton("➕ New Download", callback_data='dashboard_new_download')],
            [
                InlineKeyboardButton("📥 Downloads", callback_data='dashboard_downloads'),
                InlineKeyboardButton("⏰ Queue", callback_data='dashboard_queue')
            ],
            [
                InlineKeyboardButton("📁 My Files", callback_data='dashboard_files'),
                InlineKeyboardButton("🔍 Search", callback_data='dashboard_search')
            ],
            [
                InlineKeyboardButton("⭐ Favorites", callback_data='dashboard_favorites'),
                InlineKeyboardButton("ℹ️ Help", callback_data='dashboard_help')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🎬 *Smart Downloader*\n\n"
            "Your personal media server using Telegram as storage.\n\n"
            "💡 Send a link or use the button below!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    if action == 'dashboard_downloads':
        active = db.get_active_download()
        queue_summary = db.get_queue_summary()

        if not active and queue_summary['pending'] == 0:
            msg = "✅ No active downloads\n\nQueue is empty."
        else:
            msg = "📥 Downloads\n\n"
            if active:
                msg += f"🔄 Active: {active['title'] or 'Processing...'}\n"
                msg += f"Progress: {active['progress']}%\n"
            if queue_summary['pending'] > 0:
                msg += f"\n⏳ In Queue: {queue_summary['pending']} items"

        keyboard = [[InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup)

    elif action == 'dashboard_files':
        keyboard = [[InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📁 *My Files*\n\n"
            "Feature coming soon!\n\n"
            "Use /search to find files.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif action == 'dashboard_search':
        keyboard = [[InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔍 *Search*\n\n"
            "Usage: /search <query>\n\n"
            "Example: /search action",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif action == 'dashboard_favorites':
        favorites = db.get_favorites()
        if not favorites:
            msg = "⭐ Favorites\n\nNo favorites yet.\n\nUse /fav <media_id> to add files to favorites."
        else:
            msg = f"⭐ Favorites ({len(favorites)})\n\n"
            for item in favorites[:5]:
                title = item.get('title') or 'Untitled'
                msg += f"• {title[:30]}...\n"
            if len(favorites) > 5:
                msg += f"\n...and {len(favorites) - 5} more"

        keyboard = [[InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup)

    elif action == 'dashboard_help':
        keyboard = [[InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "ℹ️ *Help*\n\n"
            "• Send a link to download\n"
            "• Use /torrent <magnet> for torrents\n"
            "• Use /download <url> for direct links\n"
            "• Use /search <query> to find files\n"
            "• Use /status to check downloads\n"
            "• Use /userbot_setup to enable large file support\n\n",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
