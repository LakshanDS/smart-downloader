# Phase 6: Category Browser & UI

**Objective:** User interface to browse, search, and play downloaded content organized by category.

## Architecture

```
User Commands: /movie, /tv, /porn, /myfiles
       │
       ├──────────────────────────┐
       │  Category Browser       │
       │  - Fetch from database   │
       │  - Inline keyboard UI      │
       └──────────────────────────┘
       │
       ↓
┌───────────────────────────────────────────┐
│  Inline Keyboard Layout               │
│  ┌──────────┬──────────┬──────────┐  │
│  │          │          │          │  │
│  📽 Movies  📺 TV Shows  🔞 Porn    │  │
│  [+] Add    [+] Add    [+] Add    │  │
│  [Back]     [Back]     [Back]     │  │
│  └──────────┴──────────┴──────────┘  │
│         ↓                                  │
│  Click → Show items in category           │
│         ↓                                  │
│  ┌────────────────────────────┐         │
│  │ 🎬 Title Name          │         │
│  │ Size: 1.2 GB • Duration: 2h  │         │
│  │ [▶ Play] [❌ Delete]      │         │
│  └────────────────────────────┘         │
│         ↓                                  │
│  Bot forwards file_id → User sees video  │
└───────────────────────────────────────────┘
```

## Core Components

### 1. Category Browser (`category_browser.py`)

```python
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from typing import List, Dict
from database import DatabaseManager
import logging

logger = logging.getLogger(__name__)

class CategoryBrowser:
    """Handle category browsing and inline keyboards."""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Create main category selection keyboard."""
        categories = self.db.get_all_categories()
        
        keyboard = []
        row = []
        
        for cat in categories:
            btn = InlineKeyboardButton(
                text=f"{cat['icon']} {cat['name'].title()}",
                callback_data=f"cat_{cat['name']}"
            )
            row.append(btn)
            
            if len(row) == 2:  # 2 buttons per row
                keyboard.append(row)
                row = []
        
        # Add utility buttons
        row.append(InlineKeyboardButton(text="📁 My Files", callback_data="myfiles_all"))
        keyboard.append(row)
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_category_items_keyboard(self, category: str, user_id: int, 
                               chat_id: int, page: int = 1) -> InlineKeyboardMarkup:
        """Create keyboard for items in a category."""
        items_per_page = 10
        offset = (page - 1) * items_per_page
        
        # Get items with pagination
        items = self.db.get_media_by_category(category, user_id, chat_id)
        paginated_items = items[offset:offset + items_per_page]
        
        keyboard = []
        row = []
        
        for item in paginated_items:
            # Compact format: "1. Title (size)"
            title = item['title'] or 'Untitled'
            size_mb = (item.get('file_size', 0) / (1024 * 1024)) if item.get('file_size') else 0
            size_str = f"{size_mb:.1f} MB" if size_mb > 0 else "? MB"
            
            btn = InlineKeyboardButton(
                text=f"{item['id']}. {title[:30]} ({size_str})",
                callback_data=f"play_{item['id']}"
            )
            row.append(btn)
            
            if len(row) == 1:  # 1 button per row for compact view
                keyboard.append(row)
                row = []
        
        # Pagination controls
        total_pages = (len(items) + items_per_page - 1) // items_per_page
        
        if total_pages > 1:
            nav_row = []
            
            if page > 1:
                nav_row.append(InlineKeyboardButton(
                    text="◀ Prev",
                    callback_data=f"cat_{category}_p{page-1}"
                ))
            
            nav_row.append(InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="noop"
            ))
            
            if page < total_pages:
                nav_row.append(InlineKeyboardButton(
                    text="Next ▶",
                    callback_data=f"cat_{category}_p{page+1}"
                ))
            
            keyboard.append(nav_row)
        
        # Back button
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_main")])
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_item_keyboard(self, item: Dict) -> InlineKeyboardMarkup:
        """Create keyboard for a single item (play, delete)."""
        keyboard = []
        
        # Play button
        if item.get('file_id'):
            keyboard.append([
                InlineKeyboardButton(text="▶ Play", callback_data=f"play_confirm_{item['id']}")
            ])
        
        # Delete button
        keyboard.append([
            InlineKeyboardButton(text="❌ Delete", callback_data=f"delete_confirm_{item['id']}")
        ])
        
        # Back button
        keyboard.append([
            InlineKeyboardButton(text="🔙 Back", callback_data=f"cat_{item['category']}_p1")
        ])
        
        return InlineKeyboardMarkup(keyboard)
```

### 2. Bot Handlers (`bot.py` additions)

```python
# Category browsing handlers

async def handle_browse_category(update: Update, context):
    """Handle /movie, /tv, /porn commands."""
    command = update.message.text.split()[0].lstrip('/')
    category = command.lower()
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Update chat activity
    db.update_chat_activity(chat_id)
    
    # Validate category
    if not validate_category(category):
        await update.message.reply_text(f"❌ Unknown category: {category}")
        return
    
    # Get category info
    cat_info = db.get_category(category)
    
    if not cat_info:
        await update.message.reply_text("❌ Category not found")
        return
    
    browser = CategoryBrowser(db)
    keyboard = browser.get_category_items_keyboard(category, user_id, chat_id)
    
    message = f"""
{cat_info['icon']} **{cat_info['name'].title()}**

Choose an item to play or manage:
    """
    
    await update.message.reply_text(message, reply_markup=keyboard)
    db.log_activity(user_id, chat_id, 'category_browsed', {'category': category})


async def handle_my_files(update: Update, context):
    """Handle /myfiles command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    db.update_chat_activity(chat_id)
    
    library = db.get_user_library(user_id, chat_id)
    
    # Check if user has any files
    if not library or all(len(items) == 0 for items in library.values()):
        await update.message.reply_text(
            "📁 You don't have any downloaded files yet.\n\n"
            "Use /torrent <magnet> or /download <url> to get started!"
        )
        return
    
    # Build library summary
    browser = CategoryBrowser(db)
    keyboard = browser.get_main_menu_keyboard()
    
    summary = "📁 **Your Library:**\n\n"
    
    for cat_name, items in library.items():
        cat_info = db.get_category(cat_name)
        summary += f"{cat_info['icon']} {cat_name.title()}: {len(items)} items\n"
    
    summary += f"\nTotal: {sum(len(items) for items in library.values())} files"
    
    await update.message.reply_text(summary, reply_markup=keyboard)


async def handle_button_press(update: Update, context):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    data = query.data
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    browser = CategoryBrowser(db)
    
    await query.answer()
    
    # Main menu
    if data == "menu_main":
        keyboard = browser.get_main_menu_keyboard()
        await query.edit_message_text("📥 What do you want to browse?", reply_markup=keyboard)
        return
    
    # My files
    if data == "myfiles_all":
        await handle_my_files(update, context)
        return
    
    # Category selection
    if data.startswith("cat_"):
        # Parse: "cat_movie_p1" or "cat_movie"
        parts = data.split('_')
        
        if len(parts) == 2:  # Just category selection
            category = parts[1]
            keyboard = browser.get_category_items_keyboard(category, user_id, chat_id, page=1)
            
            cat_info = db.get_category(category)
            await query.edit_message_text(
                f"{cat_info['icon']} {cat_info.title()}:",
                reply_markup=keyboard
            )
            return
        
        elif len(parts) == 3:  # Pagination
            category = parts[1]
            page = int(parts[2][1:])  # "p2" -> 2
            keyboard = browser.get_category_items_keyboard(category, user_id, chat_id, page)
            
            cat_info = db.get_category(category)
            await query.edit_message_text(
                f"{cat_info['icon']} {cat_info.title()} (page {page}):",
                reply_markup=keyboard
            )
            return
    
    # Play item
    if data.startswith("play_confirm_"):
        media_id = int(data.split('_')[2])
        await handle_play_action(update, context, media_id)
        return
    
    # Delete item
    if data.startswith("delete_confirm_"):
        media_id = int(data.split('_')[2])
        await handle_delete_action(update, context, media_id)
        return
    
    # No-op
    if data == "noop":
        return
    
    await query.edit_message_text("❌ Unknown action")
```

### 3. Play & Delete Actions

```python
async def handle_play_action(update: Update, context, media_id: int):
    """Handle play button press."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Get media info
    media = db.get_media_by_id(media_id, user_id, chat_id)
    
    if not media:
        await update.message.reply_text("❌ File not found")
        return
    
    if not media.get('file_id'):
        await update.message.reply_text(
            "⏳ This file hasn't finished uploading yet.\n\n"
            "Check /status for upload progress."
        )
        return
    
    # Forward file to user
    await bot.forward_message(
        chat_id=chat_id,
        from_chat_id=chat_id,  # From bot's own message
        message_id=media.get('forward_message_id')  # Store original message ID
    )
    
    db.log_activity(user_id, chat_id, 'media_played', {'media_id': media_id})


async def handle_delete_action(update: Update, context, media_id: int):
    """Handle delete button press."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    query = update.callback_query
    
    # Get media info
    media = db.get_media_by_id(media_id, user_id, chat_id)
    
    if not media:
        await query.answer("❌ File not found", show_alert=True)
        return
    
    # Delete the message (removes file_id from bot's messages)
    await bot.delete_message(
        chat_id=media.get('chat_id') or chat_id,
        message_id=media.get('forward_message_id') or media.get('message_id')
    )
    
    # Remove from database
    db.delete_media(media_id, user_id)
    
    await query.edit_message_text(
        f"✅ Deleted: {media.get('title', 'File')}",
        reply_markup=CategoryBrowser(db).get_category_items_keyboard(
            media.get('category', 'custom'), user_id, chat_id
        )
    )
    
    db.log_activity(user_id, chat_id, 'media_deleted', {'media_id': media_id})
```

## UI Layout Examples

### Main Menu
```
📥 Smart Downloader

What do you want to do?

┌─────────┬─────────┬─────────┐
│  📽     │  📺     │  🔞     │
│ Movies   │ TV Shows │ Porn    │
└─────────┴─────────┴─────────┘
           ↓
┌──────────────────┐
│  📁 My Files   │
└──────────────────┘
```

### Category View
```
📺 TV Shows

Choose an item:

1. Breaking Bad (1.2 GB)
2. Game of Thrones (8.5 GB)
3. Stranger Things (4.1 GB)
4. The Office (3.8 GB)
5. ...

┌──────────┬──────────┐
│  ◀ Prev   │ 1/10     │  Next ▶   │
└──────────┴──────────┘
      ↓
┌──────────────────┐
│      🔙 Back     │
└──────────────────┘
```

### Item Actions
```
🎬 Breaking Bad - S01E01

Size: 1.2 GB
Duration: 1h 2m

┌────────────────┬────────────┐
│  ▶ Play     │  ❌ Delete   │
└────────────────┴────────────┘
      ↓
┌──────────────────┐
│      🔙 Back     │
└──────────────────┘
```

## Implementation Tasks

- [ ] Create `category_browser.py` with CategoryBrowser class
- [ ] Implement main menu keyboard (movies, tv, porn, myfiles)
- [ ] Add pagination for large libraries
- [ ] Implement play action (forward file_id)
- [ ] Implement delete action (delete message + DB entry)
- [ ] Add callback query handler for button presses
- [ ] Integrate with database queries
- [ ] Add category icons and formatting
- [ ] Test inline keyboard responsiveness on mobile
- [ ] Add error handling for missing files
- [ ] Add "Add to library" quick-action buttons

## Notes

- **Inline Keyboards:** Use callback_data for state tracking
- **Pagination:** Limit to 10 items per page (user preference)
- **Delete Logic:** Removes bot message, clears file_id reference
- **Play Logic:** Forwards existing message with file_id (bypasses 50 MB limit)
