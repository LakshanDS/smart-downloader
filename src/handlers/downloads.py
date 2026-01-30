"""
Download Manager Handler - Smart Downloader

Shows active downloads with individual controls, progress, speed, ETA, and queue counter.
Auto-refreshes every 3 seconds when downloads are active.
"""

import asyncio
import logging
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.error import BadRequest

from database.manager import DatabaseManager
import shared.state as state

logger = logging.getLogger(__name__)

REFRESH_INTERVAL = 3


def clean_filename(title: str, max_length: int = 32) -> str:
    """Clean filename: remove emojis, special chars, trim to max_length."""
    if not title:
        return "Unknown"

    # Remove emojis and wide unicode chars
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        u"\U0001F900-\U0001F9FF"  # supplemental symbols
        u"\U00002600-\U000026FF"
        u"\U0000FE0F"
        "]+", flags=re.UNICODE)
    title = emoji_pattern.sub('', title)

    # Remove special chars, keep alphanumeric, spaces, dots, dashes, underscores
    title = re.sub(r'[^\w\s\.\-_]', '', title)

    # Remove extra whitespace
    title = ' '.join(title.split())

    # Trim to max length
    if len(title) > max_length:
        title = title[:max_length] + '...'

    result = title or "Unknown"

    # Escape markdown special characters
    for char in ['*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        result = result.replace(char, '\\' + char)

    return result


def format_speed(speed_bytes: float) -> str:
    """Format speed to human readable."""
    if not speed_bytes:
        return "0.00 MB/s"
    speed_mb = speed_bytes / (1024 * 1024)
    return f"{speed_mb:.2f} MB/s"


def format_size(size_bytes: int) -> str:
    """Format size to human readable."""
    if not size_bytes:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def format_eta(seconds: int) -> str:
    """Format ETA to human readable."""
    if not seconds or seconds <= 0:
        return "Calculating..."
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"


def create_progress_bar(progress: int, width: int = 20) -> str:
    """Create visual progress bar."""
    filled = int(width * progress / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}]"


def get_download_status_emoji(status: str, paused: bool = False) -> str:
    """Get emoji for download status."""
    if paused:
        return "⏸️"
    if status == 'downloading':
        return "📥"
    if status == 'uploading':
        return "📤"
    if status == 'pending':
        return "⏳"
    if status == 'completed':
        return "✅"
    if status == 'failed':
        return "❌"
    return "❓"


async def auto_refresh_loop(chat_id: int, message_id: int, context: CallbackContext, db: DatabaseManager):
    """Background task to auto-refresh Download Manager every 3 seconds."""
    try:
        # Continue refreshing for 30 seconds after downloads complete
        post_completion_seconds = 30
        no_download_count = 0

        while True:
            await asyncio.sleep(REFRESH_INTERVAL)

            # Check if still active
            if chat_id not in state.active_download_managers:
                break

            active_downloads = db.get_all_active_downloads()

            if not active_downloads:
                # No active downloads - count down to show completion briefly
                no_download_count += REFRESH_INTERVAL
                if no_download_count >= post_completion_seconds:
                    # Time's up, stop auto-refresh
                    del state.active_download_managers[chat_id]
                    break
            else:
                # Reset counter when downloads are active
                no_download_count = 0

            # Update message (pass empty list if no downloads, will show recent)
            await _update_download_manager_message(chat_id, message_id, context, db, active_downloads)
    except asyncio.CancelledError:
        logger.debug(f"Auto-refresh loop cancelled for chat {chat_id}")
    except Exception as e:
        logger.error(f"Auto-refresh loop error for chat {chat_id}: {e}")
        if chat_id in state.active_download_managers:
            del state.active_download_managers[chat_id]


async def _update_download_manager_message(chat_id: int, message_id: int, context: CallbackContext,
                                           db: DatabaseManager, active_downloads: list):
    """Update the Download Manager message with current data."""
    try:
        # Build message
        message_lines = ["📥 **Download Manager**", "━━━━━━━━━━━━━━━━━━━━━"]

        # Show active download first
        active = None
        for dl in active_downloads:
            if dl['status'] == 'downloading' or (dl['status'] == 'pending' and not active):
                active = dl
                break

        # If no active downloads, show most recent (for post-completion display)
        recent = None
        if not active:
            recent = db.get_most_recent_download()

        display_item = active or recent

        if display_item:
            position, total = db.get_queue_position(display_item['id'])
            paused = bool(display_item.get('paused', 0))

            status_emoji = get_download_status_emoji(display_item['status'], paused)

            progress = display_item.get('progress', 0) or 0
            dl_speed = display_item.get('download_speed') or 0
            ul_speed = display_item.get('upload_speed') or 0
            eta = display_item.get('eta_seconds') or 0
            file_size = display_item.get('file_size')

            message_lines.extend([
                f"",
                f"**{status_emoji} Active Download** ({position}/{total})" if total > 0 else f"**{status_emoji} Active Download**",
                f"{create_progress_bar(progress)} {progress}%",
                f"⏱️ ETA: {format_eta(eta)}",
                f"↓ {format_speed(dl_speed)} | ↑ {format_speed(ul_speed)}",
            ])

            if file_size:
                downloaded = (file_size * progress / 100) if progress > 0 else 0
                message_lines.append(f"📊 {format_size(int(downloaded))} / {format_size(file_size)}")

        # Show next item in queue only
        queued = [dl for dl in active_downloads if dl['id'] != (active['id'] if active else None)]
        if queued:
            next_item = queued[0]
            next_title = clean_filename(next_item.get('title') or next_item['url'])
            position, total = db.get_queue_position(next_item['id'])
            message_lines.extend([
                f"",
                f"**📋 Up Next:** ({position}/{total})",
                f"⏳ {next_title}"
            ])
            if len(queued) > 1:
                message_lines.append(f"... and {len(queued) - 1} more in queue")

        message = "\n".join(message_lines)

        # Build keyboard
        keyboard = []

        if active:
            download_id = active['id']
            paused = bool(active.get('paused', 0))
            can_pause = bool(active.get('can_pause', 1))

            if paused:
                keyboard.append([
                    InlineKeyboardButton("▶ Resume", callback_data=f"dm_resume_{download_id}"),
                    InlineKeyboardButton("✕ Cancel", callback_data=f"dm_cancel_{download_id}")
                ])
            else:
                if active['status'] == 'downloading' and can_pause:
                    keyboard.append([
                        InlineKeyboardButton("⏸ Pause", callback_data=f"dm_pause_{download_id}"),
                        InlineKeyboardButton("✕ Cancel", callback_data=f"dm_cancel_{download_id}")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton("✕ Cancel", callback_data=f"dm_cancel_{download_id}")
                    ])

        # New download button (no refresh button - auto-refresh enabled)
        keyboard.append([
            InlineKeyboardButton("➕ New Download", callback_data="dashboard_new_download")
        ])

        # Back button
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="dashboard_back")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except BadRequest as e:
        if "not modified" in str(e).lower():
            pass
        elif "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
            # Message deleted or user navigated away
            if chat_id in state.active_download_managers:
                del state.active_download_managers[chat_id]
        else:
            logger.warning(f"BadRequest in auto-refresh: {e}")
    except Exception as e:
        logger.warning(f"Failed to auto-refresh download manager: {e}")


async def show_download_manager(update: Update, context: CallbackContext, db: DatabaseManager):
    """Show the download manager interface."""
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id

    # Cancel any existing auto-refresh for this chat
    if chat_id in state.active_download_managers:
        old_task = state.active_download_managers[chat_id].get('task')
        if old_task and not old_task.done():
            old_task.cancel()

    # Get all active downloads
    active_downloads = db.get_all_active_downloads()

    if not active_downloads:
        message = """📥 **Download Manager**
━━━━━━━━━━━━━━━━━━━━━

Active downloads will appear here."""
        keyboard = [
            [InlineKeyboardButton("➕ New Download", callback_data="dashboard_new_download")],
            [InlineKeyboardButton("⬅️ Back", callback_data="dashboard_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text=message, parse_mode='Markdown', reply_markup=reply_markup)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                logger.warning(f"BadRequest editing empty download manager: {e}")
        return

    # Build message
    message_lines = ["📥 **Download Manager**", "━━━━━━━━━━━━━━━━━━━━━"]

    # Show active download first
    active = None
    for dl in active_downloads:
        if dl['status'] == 'downloading' or (dl['status'] == 'pending' and not active):
            active = dl
            break

    if active:
        position, total = db.get_queue_position(active['id'])
        paused = bool(active.get('paused', 0))

        status_emoji = get_download_status_emoji(active['status'], paused)
        # Clean filename - remove emojis, symbols, trim to 32 chars
        title = clean_filename(active.get('title') or active['url'])

        progress = active.get('progress', 0) or 0
        dl_speed = active.get('download_speed') or 0
        ul_speed = active.get('upload_speed') or 0
        eta = active.get('eta_seconds') or 0
        file_size = active.get('file_size')

        message_lines.extend([
            f"",
            f"**{status_emoji} Active Download** ({position}/{total})" if total > 0 else f"**{status_emoji} Active Download**",
            f"📄 {title}",
            f"{create_progress_bar(progress)} {progress}%",
            f"⏱️ ETA: {format_eta(eta)}",
            f"↓ {format_speed(dl_speed)} | ↑ {format_speed(ul_speed)}",
        ])

        if file_size:
            downloaded = (file_size * progress / 100) if progress > 0 else 0
            message_lines.append(f"📊 {format_size(int(downloaded))} / {format_size(file_size)}")

    # Show next item in queue only
    queued = [dl for dl in active_downloads if dl['id'] != (active['id'] if active else None)]
    if queued:
        next_item = queued[0]
        next_title = clean_filename(next_item.get('title') or next_item['url'])
        position, total = db.get_queue_position(next_item['id'])
        message_lines.extend([
            f"",
            f"**📋 Up Next:** ({position}/{total})",
            f"⏳ {next_title}"
        ])
        if len(queued) > 1:
            message_lines.append(f"... and {len(queued) - 1} more in queue")

    message = "\n".join(message_lines)

    # Build keyboard
    keyboard = []

    if active:
        download_id = active['id']
        paused = bool(active.get('paused', 0))
        can_pause = bool(active.get('can_pause', 1))  # Check if pauseable

        if paused:
            keyboard.append([
                InlineKeyboardButton("▶ Resume", callback_data=f"dm_resume_{download_id}"),
                InlineKeyboardButton("✕ Cancel", callback_data=f"dm_cancel_{download_id}")
            ])
        else:
            if active['status'] == 'downloading' and can_pause:
                keyboard.append([
                    InlineKeyboardButton("⏸ Pause", callback_data=f"dm_pause_{download_id}"),
                    InlineKeyboardButton("✕ Cancel", callback_data=f"dm_cancel_{download_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("✕ Cancel", callback_data=f"dm_cancel_{download_id}")
                ])

    # New download button (no refresh button - auto-refresh enabled)
    keyboard.append([
        InlineKeyboardButton("➕ New Download", callback_data="dashboard_new_download")
    ])

    # Back button - use universal dashboard_back callback
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="dashboard_back")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        sent_message = await query.edit_message_text(
            text=message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

        # Start auto-refresh task
        message_id = sent_message.message_id
        task = asyncio.create_task(auto_refresh_loop(chat_id, message_id, context, db))
        state.active_download_managers[chat_id] = {'message_id': message_id, 'task': task}
        logger.debug(f"Started auto-refresh for chat {chat_id}, message {message_id}")

    except BadRequest as e:
        # Ignore "not modified" errors - content hasn't changed
        if "not modified" not in str(e).lower():
            logger.warning(f"BadRequest editing download manager: {e}")
    except Exception as e:
        logger.warning(f"Failed to edit download manager message: {e}")


async def handle_pause(update: Update, context: CallbackContext, db: DatabaseManager):
    """Handle pause button - updates DB, pooler respects the change."""
    query = update.callback_query
    await query.answer("Pausing...")

    try:
        download_id = int(query.data.split("_")[-1])

        # Check if download can be paused
        download = db.get_download(download_id)
        if not download or not bool(download.get('can_pause', 1)):
            await query.answer("❌ This download cannot be paused")
            return

        # Set paused flag in database - pooler will skip this item
        db.set_paused(download_id, paused=True, reason="Paused by user via download manager")
        logger.info(f"Paused download {download_id}")
        await show_download_manager(update, context, db)
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse download_id from callback data: {query.data}")
        await query.answer("Error: Invalid download ID")


async def handle_resume(update: Update, context: CallbackContext, db: DatabaseManager):
    """Handle resume button - updates DB, pooler will pick it up."""
    query = update.callback_query
    await query.answer("Resuming...")

    try:
        download_id = int(query.data.split("_")[-1])
        # Clear paused flag - pooler can now process this item
        db.set_paused(download_id, paused=False)
        logger.info(f"Resumed download {download_id}")
        await show_download_manager(update, context, db)
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse download_id from callback data: {query.data}")
        await query.answer("Error: Invalid download ID")


async def handle_cancel(update: Update, context: CallbackContext, db: DatabaseManager):
    """Handle cancel button - marks as failed in DB."""
    query = update.callback_query
    await query.answer("Cancelling...")

    try:
        download_id = int(query.data.split("_")[-1])
        # Mark as failed/cancelled in database
        db.cancel_download(download_id)
        logger.info(f"Cancelled download {download_id}")
        await show_download_manager(update, context, db)
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse download_id from callback data: {query.data}")
        await query.answer("Error: Invalid download ID")
