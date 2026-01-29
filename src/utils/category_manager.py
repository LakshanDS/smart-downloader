"""
Category Manager - Phase 9
Handle category CRUD operations for content organization.
"""

import logging
from typing import List, Dict, Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class CategoryManager:
    """Handle category CRUD operations."""

    def __init__(self, db):
        """
        Initialize category manager.

        Args:
            db: DatabaseManager instance
        """
        self.db = db

    async def list_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all categories with item counts."""
        try:
            categories = self.db.get_all_categories()

            if not categories:
                await update.message.reply_text(
                    "📁 No categories yet.\n\n"
                    "Use /category create <name> [emoji] to create one."
                )
                return

            # Get item counts for each category
            message = "📁 **My Categories:**\n\n"

            for cat in categories:
                count = len(self.db.get_media_by_category(cat['id']))
                message += f"{cat['emoji']} **{cat['name']}** - {count} files\n"

            message += f"\n\nTotal: {len(categories)} categories"
            message += "\n\nUse /category create <name> [emoji] to add more."

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error listing categories: {e}")
            await update.message.reply_text("❌ Failed to list categories")

    async def create_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create a new category."""
        try:
            args = context.args

            if not args:
                await update.message.reply_text(
                    "Usage: /category create <name> [emoji]\n"
                    "Example: /category create Action Movies 🎬"
                )
                return

            name = args[0]
            emoji = args[1] if len(args) > 1 else '📁'

            # Validate emoji (basic check)
            if len(emoji) > 4:
                await update.message.reply_text("❌ Emoji too long (max 4 characters)")
                return

            try:
                cat_id = self.db.create_category(name, emoji)
                await update.message.reply_text(
                    f"✅ Category created!\n\n"
                    f"{emoji} **{name}**\n"
                    f"ID: {cat_id}"
                )
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    await update.message.reply_text("❌ Category already exists")
                else:
                    logger.error(f"Failed to create category: {e}")
                    await update.message.reply_text("❌ Failed to create category")

        except Exception as e:
            logger.error(f"Error creating category: {e}")
            await update.message.reply_text("❌ Failed to create category")

    async def delete_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete a category."""
        try:
            args = context.args

            if not args:
                await update.message.reply_text("Usage: /category delete <name>")
                return

            name = args[0]

            # Find category
            categories = self.db.get_all_categories()
            cat = next((c for c in categories if c['name'].lower() == name.lower()), None)

            if not cat:
                await update.message.reply_text(f"❌ Category '{name}' not found")
                return

            # Delete
            self.db.delete_category(cat['id'])
            await update.message.reply_text(f"✅ Category '{name}' deleted")

        except Exception as e:
            logger.error(f"Error deleting category: {e}")
            await update.message.reply_text("❌ Failed to delete category")

    async def rename_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Rename a category."""
        try:
            args = context.args

            if len(args) < 2:
                await update.message.reply_text("Usage: /category rename <old> <new>")
                return

            old_name = args[0]
            new_name = args[1]

            # Find category
            categories = self.db.get_all_categories()
            cat = next((c for c in categories if c['name'].lower() == old_name.lower()), None)

            if not cat:
                await update.message.reply_text(f"❌ Category '{old_name}' not found")
                return

            # Rename
            self.db.rename_category(cat['id'], new_name)
            await update.message.reply_text(f"✅ Renamed '{old_name}' → '{new_name}'")

        except Exception as e:
            logger.error(f"Error renaming category: {e}")
            await update.message.reply_text("❌ Failed to rename category")

    async def show_add_category_keyboard(self, media_id: int, update: Update):
        """Show category selection keyboard for adding media to categories."""
        try:
            categories = self.db.get_all_categories()

            if not categories:
                await update.message.reply_text(
                    "❌ No categories.\n"
                    "Use /category create <name> [emoji] to create one first."
                )
                return

            keyboard = []
            row = []

            for cat in categories:
                # Check if media already in category
                media_cats = self.db.get_media_categories(media_id)
                is_in_cat = any(c['id'] == cat['id'] for c in media_cats)

                prefix = "☑️ " if is_in_cat else "⬜ "
                btn = InlineKeyboardButton(
                    text=f"{prefix}{cat['emoji']} {cat['name']}",
                    callback_data=f"addcat_{media_id}_{cat['id']}"
                )
                row.append(btn)

                if len(row) == 2:
                    keyboard.append(row)
                    row = []

            if row:
                keyboard.append(row)

            # Add Done button
            keyboard.append([InlineKeyboardButton(text="✅ Done", callback_data=f"addcat_done_{media_id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Select categories:", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error showing category keyboard: {e}")
            await update.message.reply_text("❌ Failed to show categories")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle category selection callback."""
        try:
            query = update.callback_query
            await query.answer()

            data = query.data

            if data.startswith('addcat_'):
                parts = data.split('_')
                action = parts[1]

                if action == 'done':
                    # Done selecting categories
                    await query.edit_message_text("✅ Categories updated!")

                else:
                    # Toggle category for media
                    media_id = int(parts[1])
                    cat_id = int(parts[2])

                    # Toggle membership
                    media_cats = self.db.get_media_categories(media_id)
                    is_in_cat = any(c['id'] == cat_id for c in media_cats)

                    if is_in_cat:
                        self.db.remove_media_from_category(media_id, cat_id)
                    else:
                        self.db.add_media_to_category(media_id, cat_id)

                    # Refresh keyboard
                    await self.show_add_category_keyboard(media_id, update)

        except Exception as e:
            logger.error(f"Error handling callback: {e}")


class FileBrowser:
    """Browse media library with pagination."""

    ITEMS_PER_PAGE = 10

    def __init__(self, db):
        """
        Initialize file browser.

        Args:
            db: DatabaseManager instance
        """
        self.db = db

    async def show_all_files(self, update: Update, page: int = 1):
        """Show all files with pagination."""
        try:
            # Get all media
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM media
                    ORDER BY created_at DESC
                """)
                all_items = [dict(row) for row in cursor.fetchall()]

            # Paginate
            offset = (page - 1) * self.ITEMS_PER_PAGE
            items = all_items[offset:offset + self.ITEMS_PER_PAGE]
            total_pages = max(1, (len(all_items) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE)

            if not items:
                await update.message.reply_text("📁 No files yet.\n\nDownload something first!")
                return

            # Build message
            message = f"📁 **My Files** (Page {page}/{total_pages})\n\n"

            for item in items:
                title = item.get('title') or 'Untitled'
                size_mb = (item.get('file_size', 0) / (1024 * 1024)) if item.get('file_size') else 0
                size_str = f"{size_mb:.1f} MB" if size_mb > 0 else "? MB"
                fav = "⭐ " if item.get('is_favorite') else ""

                message += f"{item['id']}. {fav}{title}\n"
                message += f"   📏 {size_str}\n\n"

            # Pagination buttons
            keyboard = []
            row = []

            if page > 1:
                row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"files_page_{page-1}"))

            if page < total_pages:
                row.append(InlineKeyboardButton("Next ➡️", callback_data=f"files_page_{page+1}"))

            if row:
                keyboard.append(row)

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error showing files: {e}")
            await update.message.reply_text("❌ Failed to show files")


class SearchHandler:
    """Handle media search functionality."""

    def __init__(self, db):
        """
        Initialize search handler.

        Args:
            db: DatabaseManager instance
        """
        self.db = db

    async def handle_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command."""
        try:
            args = context.args

            if not args:
                await update.message.reply_text("Usage: /search <query>")
                return

            query = ' '.join(args)

            # Search
            results = self.db.search_media(query)

            if not results:
                await update.message.reply_text(f"❌ No results for '{query}'")
                return

            message = f"🔍 **Search Results:** '{query}'\n\n"

            for item in results[:10]:  # Limit to 10 results
                title = item.get('title') or 'Untitled'
                message += f"• {title}\n"

            if len(results) > 10:
                message += f"\n...and {len(results) - 10} more"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error searching: {e}")
            await update.message.reply_text("❌ Failed to search")

    async def handle_favorites(self, update: Update):
        """Handle /favorites command."""
        try:
            # Get favorited media
            favorites = self.db.get_favorites()

            if not favorites:
                await update.message.reply_text("⭐ No favorites yet.\n\nUse /fav <media_id> to add favorites.")
                return

            message = "⭐ **My Favorites:**\n\n"

            for item in favorites:
                title = item.get('title') or 'Untitled'
                message += f"• {title} (ID: {item['id']})\n"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error showing favorites: {e}")
            await update.message.reply_text("❌ Failed to show favorites")
