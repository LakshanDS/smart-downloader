# Phase 8: Content Organization & Category Management

**Objective:** User-created categories with CRUD operations, file browser, favorites, and search.

## Key Changes from Original Plan

- **User-created categories**: No fixed categories, users create their own folders
- **Many-to-many relationship**: Files can be in multiple categories
- **Category CRUD commands**: Create, rename, delete categories
- **Add to category workflow**: Select files, add to one or more categories

## Architecture

```
User Commands: /myfiles, /categories, /search, /favorites
       │
       ├──────────────────────────┐
       │  Category Browser       │
       │  - List all categories   │
       │  - Category CRUD         │
       │  - Inline keyboard UI      │
       └──────────────────────────┘
       │
       ↓
┌───────────────────────────────────────────┐
│  Inline Keyboard Layout               │
│  ┌────────────────────────────────┐    │
│  │ 📁 My Categories (5)            │    │
│  │                                 │    │
│  │ 🎬 Action Movies [12]          │    │
│  │ 😂 Comedy [8]                  │    │
│  │ ❤️ Favorites [3]                │    │
│  │ ⏰ Watch Later [5]             │    │
│  │                                 │    │
│  │ [➕ New] [⚙️ Manage]            │    │
│  └────────────────────────────────┘    │
│         ↓                                  │
│  Click → Show items in category           │
│         ↓                                  │
│  ┌────────────────────────────┐         │
│  │ 🎬 Title Name          │         │
│  │ Size: 1.2 GB • Duration: 2h  │         │
│  │ [▶ Play] [📂+] [❌ Delete]  │         │
│  └────────────────────────────┘         │
│         ↓                                  │
│  [📂+] → Select categories to add          │
│  Bot forwards file_id → User sees video  │
└───────────────────────────────────────────┘
```

## Commands

| Command | Description |
|---------|-------------|
| `/myfiles` | Browse all files (paginated) |
| `/categories` | List all categories |
| `/category create <name> [emoji]` | Create new category |
| `/category delete <name>` | Delete category |
| `/category rename <old> <new>` | Rename category |
| `/category add <file_id> <category>` | Add file to category |
| `/category remove <file_id> <category>` | Remove from category |
| `/search <query>` | Search media library |
| `/favorites` | View favorited items |

## Core Components

### 1. Category Management (`category_manager.py`)

```python
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from database import DatabaseManager
import logging

logger = logging.getLogger(__name__)

class CategoryManager:
    """Handle category CRUD operations."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def list_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all categories with item counts."""
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

    async def create_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create a new category."""
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
            if "UNIQUE" in str(e):
                await update.message.reply_text("❌ Category already exists")
            else:
                logger.error(f"Failed to create category: {e}")
                await update.message.reply_text("❌ Failed to create category")

    async def delete_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete a category."""
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

    async def rename_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Rename a category."""
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
```

### 2. Add to Category Workflow

```python
async def show_add_category_keyboard(self, media_id: int, update: Update):
    """Show category selection keyboard."""
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
```

### 3. File Browser (`file_browser.py`)

```python
class FileBrowser:
    """Browse media library with pagination."""

    ITEMS_PER_PAGE = 10

    async def show_all_files(self, update: Update, page: int = 1):
        """Show all files with pagination."""
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
        total_pages = (len(all_items) + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE

        # Build message
        message = f"📁 **My Files** (Page {page}/{total_pages})\n\n"

        for item in items:
            title = item['title'] or 'Untitled'
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
```

### 4. Search Handler

```python
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command."""
    args = context.args

    if not args:
        await update.message.reply_text("Usage: /search <query>")
        return

    query = ' '.join(args)

    # Search
    results = db.search_media(query)

    if not results:
        await update.message.reply_text(f"❌ No results for '{query}'")
        return

    message = f"🔍 **Search Results:** '{query}'\n\n"

    for item in results[:10]:  # Limit to 10 results
        title = item['title'] or 'Untitled'
        message += f"• {title}\n"

    if len(results) > 10:
        message += f"\n...and {len(results) - 10} more"

    await update.message.reply_text(message, parse_mode='Markdown')
```

## Implementation Tasks

- [ ] Create `category_manager.py` with CRUD operations
- [ ] Create `file_browser.py` with pagination
- [ ] Implement `/myfiles` command with pagination
- [ ] Implement `/categories` list command
- [ ] Implement `/category create` command
- [ ] Implement `/category delete` command
- [ ] Implement `/category rename` command
- [ ] Implement add-to-category workflow (inline keyboard)
- [ ] Implement `/search` command (FTS)
- [ ] Implement `/favorites` command
- [ ] Handle callback queries for inline keyboards
- [ ] Test with multiple categories per file

## Dependencies

```python
# No additional dependencies (uses existing)
```

## Notes

- **Many-to-many**: Files can be in multiple categories
- **Junction table**: `media_categories` links files to categories
- **Cascade delete**: Deleting category removes associations but not media
- **No hierarchy**: Flat category structure (simpler UI)
- **Emoji support**: Each category can have custom emoji
- **Max categories**: Recommended 50 (reasonable limit for personal use)
