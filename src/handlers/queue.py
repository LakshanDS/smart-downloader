"""Queue management handlers - CRUD operations for download queue."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from shared.state import db
from shared.auth import check_authorized

logger = logging.getLogger(__name__)


async def show_queue_view(query):
    """Display queue management with all items."""
    queue_items = db.get_queue_items('pending')

    if not queue_items:
        msg = "⏰ *Queue*\n\nNo items in queue."
        keyboard = [
            [InlineKeyboardButton("➕ Add Download", callback_data='dashboard_new_download')],
            [InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')]
        ]
    else:
        msg = f"⏰ *Queue* ({len(queue_items)} items)\n\n"
        keyboard = []

        for idx, item in enumerate(queue_items[:10], 1):
            title = item.get('title') or 'Untitled'
            url = item.get('url', '')

            if len(title) > 30:
                title = title[:27] + "..."

            url_display = url[:40] + "..." if len(url) > 40 else url
            item_text = f"{idx}. {title}\n   `{url_display}`"
            msg += item_text + "\n\n"

            row = [
                InlineKeyboardButton(f"⬇️ #{idx}", callback_data=f'queue_download_{item["id"]}'),
                InlineKeyboardButton(f"🗑️", callback_data=f'queue_delete_{item["id"]}'),
                InlineKeyboardButton(f"⬆️", callback_data=f'queue_move_up_{item["id"]}')
            ]
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("➕ Add Download", callback_data='dashboard_new_download')])
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
    except BadRequest as e:
        if "not modified" in str(e):
            pass  # Message unchanged, ignore
        else:
            raise


async def handle_queue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle queue management callbacks."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    action = query.data

    logger.debug(f"[QUEUE] callback: {action} from chat_id={chat_id}")

    if not check_authorized(chat_id):
        await query.edit_message_text("❌ You are not authorized to use this bot.")
        return

    if action == 'dashboard_queue':
        logger.debug(f"[QUEUE] showing queue view")
        await show_queue_view(query)
        return

    # Handle queue_* actions
    if not action.startswith('queue_'):
        return

    parts = action.split('_')
    queue_action = parts[1]
    item_id = None

    # Handle move_up/move_down separately (format: queue_move_up_id)
    if queue_action == 'move' and len(parts) >= 4:
        direction = parts[2]
        item_id = int(parts[3])

        # Get current queue to find swap target
        queue_items = db.get_queue_items('pending')

        # Find current item position
        current_idx = None
        for idx, item in enumerate(queue_items):
            if item['id'] == item_id:
                current_idx = idx
                break

        if current_idx is None:
            await query.answer("❌ Item not found")
            return

        # Calculate target position
        if direction == 'up':
            if current_idx == 0:
                await query.answer("⬆️ Already at top")
                return
            target_idx = current_idx - 1
            await query.answer("⬆️ Moved up")
        else:
            if current_idx >= len(queue_items) - 1:
                await query.answer("⬇️ Already at bottom")
                return
            target_idx = current_idx + 1
            await query.answer("⬇️ Moved down")

        # Initialize priorities if all are 0 (first move operation)
        all_zero = all(item.get('priority', 0) == 0 for item in queue_items)
        if all_zero:
            # Assign priorities based on current display order (higher = earlier)
            for idx, item in enumerate(queue_items):
                # Priority 100, 90, 80, 70... (higher priority = shows first)
                new_priority = 100 - (idx * 10)
                db.set_queue_priority(item['id'], new_priority)
            logger.info(f"Initialized queue priorities for {len(queue_items)} items")

            # Re-fetch to get updated priorities
            queue_items = db.get_queue_items('pending')

        # Now swap - get items with updated priorities
        current_item = None
        target_item = None
        for item in queue_items:
            if item['id'] == item_id:
                current_item = item
            elif item['id'] == queue_items[target_idx]['id']:
                target_item = item

        if not current_item or not target_item:
            await query.answer("❌ Swap failed")
            return

        current_priority = current_item.get('priority', 0)
        target_priority = target_item.get('priority', 0)

        db.set_queue_priority(item_id, target_priority)
        db.set_queue_priority(target_item['id'], current_priority)

        logger.info(f"Swapped queue items: {item_id} (priority {current_priority}->{target_priority}) <-> {target_item['id']} ({target_priority}->{current_priority})")

        # Refresh queue view to show new order
        await show_queue_view(query)
        return

    item_id = int(parts[2]) if len(parts) > 2 else None

    if queue_action == 'download' and item_id:
        db.set_queue_priority(item_id, priority=999)
        logger.info(f"Queue item {item_id} set to download now")

        await query.answer("⬇️ Moved to front of queue!")
        await query.edit_message_text(
            "✅ Item moved to front of queue!\n\nPosition: 1 (next to download)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data='dashboard_queue')]])
        )

    elif queue_action == 'delete' and item_id:
        if db.delete_queue_item(item_id):
            logger.info(f"Deleted queue item {item_id}")
            await query.answer("🗑️ Item deleted")
            # Refresh queue view to show updated list
            await show_queue_view(query)
        else:
            await query.answer("❌ Failed to delete")

# Edit mode removed - users can delete and re-add items instead
