"""Help handlers - unified help system for all commands."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.auth import require_auth

logger = logging.getLogger(__name__)


# Help topics with their content
HELP_TOPICS = {
    'main': """📥 **Smart Downloader Help**

**Download:**
• Click "➕ New Download" button
• Send links (up to 30)
• Click "✅ Done" to finish

**Browse Commands:**
`/myfiles` - View your library
`/search <query>` - Search files
`/favorites` - Watch later list

**Management:**
`/status` - Active downloads

**Setup:**
`/userbot_setup` - Configure 2GB file support

**All downloads are processed sequentially, one at a time.**""",

    'downloads': """📥 **Downloads Help**

**How to Download:**
1. Click "➕ New Download" button
2. Send links (up to 30 at once)
3. Click "✅ Done" when finished

**Supported:**
• Magnet links (torrents)
• Direct URLs (videos, files)
• YouTube and video sites (yt-dlp)

**File Limits:**
• Standard bot: 50MB
• With userbot: 2GB""",

    'queue': """⏰ **Queue Help**

**Queue Management:**
• Items process one at a time
• Queue preserves order
• Move items up/down to prioritize

**Actions:**
⬇️ - Download now (move to front)
🗑️ - Delete from queue
⬆️/⬇️ - Reorder items

**Tips:**
• Add multiple links before clicking Done
• Use queue to prioritize downloads""",

    'search': """🔍 **Search Help**

**Commands:**
`/search <query>` - Search your files

**Example:**
`/search action` - Find "action" in filenames

**Coming Soon:**
• Advanced filters
• Search by date
• Search by size""",

    'favorites': """⭐ **Favorites Help**

**Commands:**
`/fav <media_id>` - Add to favorites
`/favorites` - View favorites list

**Use For:**
• Watch later list
• Quick access to frequently used files""",

    'userbot': """🤖 **Userbot Setup Help**

**Why Setup Userbot?**
• Standard bot limit: 50MB
• Userbot limit: 2GB

**What You Need:**
1️⃣ API ID from my.telegram.org
2️⃣ API Hash from my.telegram.org
3️⃣ Your phone number

**Setup:**
`/userbot_setup` - Start setup wizard

**Getting Credentials:**
• Visit https://my.telegram.org
• Login → "API development tools"
• Create app → Copy API ID & Hash""",

    'status': """📊 **Status Help**

**Commands:**
`/status` - View active download

**Shows:**
• Current download progress
• Download/Upload speeds
• Estimated time remaining
• Queue position for next items

**Progress Bar:**
`[████████░░░░░░░░░░] 40%`"""
}


def get_help_keyboard(topic: str = 'main') -> InlineKeyboardMarkup:
    """Generate help navigation keyboard."""
    buttons = []

    # Topic rows
    if topic != 'main':
        buttons.append([InlineKeyboardButton("📋 Main Help", callback_data='help_main')])

    buttons.extend([
        [InlineKeyboardButton("📥 Downloads", callback_data='help_downloads')],
        [InlineKeyboardButton("⏰ Queue", callback_data='help_queue')],
        [InlineKeyboardButton("🔍 Search", callback_data='help_search')],
        [InlineKeyboardButton("⭐ Favorites", callback_data='help_favorites')],
        [InlineKeyboardButton("🤖 Userbot Setup", callback_data='help_userbot')],
        [InlineKeyboardButton("📊 Status", callback_data='help_status')],
        [InlineKeyboardButton("◀️ Back", callback_data='dashboard_back')],
    ])

    return InlineKeyboardMarkup(buttons)


async def show_help_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str = 'main'):
    """Show help topic - works for both messages and callbacks."""
    help_text = HELP_TOPICS.get(topic, HELP_TOPICS['main'])
    keyboard = get_help_keyboard(topic)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            help_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            help_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )


@require_auth
async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - show main help."""
    await show_help_topic(update, context, 'main')


async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help topic navigation callbacks."""
    query = update.callback_query
    await query.answer()

    action = query.data

    if action.startswith('help_'):
        topic = action.replace('help_', '')
        logger.debug(f"[HELP] showing topic: {topic}")
        await show_help_topic(update, context, topic)
