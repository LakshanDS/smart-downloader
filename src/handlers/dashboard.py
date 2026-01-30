"""Dashboard handlers - inline keyboard callbacks."""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, link_submission_mode, active_download_managers
from shared.auth import require_auth

logger = logging.getLogger(__name__)


async def show_main_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """Show the main dashboard. Can edit existing message or send new one."""
    keyboard = [
        [InlineKeyboardButton("➕ New Download", callback_data='dashboard_new_download')],
        [
            InlineKeyboardButton("📥 Downloads", callback_data='dm_open'),
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

    message = (
        "🎬 *Smart Downloader*\n\n"
        "Your personal media server using Telegram as storage.\n\n"
        "💡 Send a link or use the button below!"
    )

    if query:
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


@require_auth
async def handle_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dashboard button callbacks."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    action = query.data

    logger.debug(f"[DASHBOARD] callback: {action} from chat_id={chat_id}")

    # Skip queue callbacks - handled by handle_queue_callback
    if action.startswith('dashboard_queue') or action.startswith('queue_'):
        logger.debug(f"[DASHBOARD] skipping queue callback: {action}")
        return

    if action == 'dashboard_new_download':
        from handlers.newurls import show_new_url_prompt
        await show_new_url_prompt(update, context)
        return

    if action == 'dashboard_back':
        # Cancel auto-refresh task if active
        if chat_id in active_download_managers:
            task = active_download_managers[chat_id].get('task')
            if task and not task.done():
                task.cancel()
            del active_download_managers[chat_id]
            logger.debug(f"Cancelled auto-refresh for chat {chat_id}")

        if chat_id in link_submission_mode:
            del link_submission_mode[chat_id]
        await show_main_dashboard(update, context, query)
        return

    if action == 'dashboard_files':
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
        from handlers.help import show_help_topic
        await show_help_topic(update, context, 'main')
        return

    # Download manager callbacks
    elif action.startswith('dm_'):
        from handlers.downloads import (
            show_download_manager,
            handle_pause,
            handle_resume,
            handle_cancel
        )

        if action == 'dm_open':
            await show_download_manager(update, context, db)
        elif action.startswith('dm_pause_'):
            await handle_pause(update, context, db)
        elif action.startswith('dm_resume_'):
            await handle_resume(update, context, db)
        elif action.startswith('dm_cancel_'):
            await handle_cancel(update, context, db)
