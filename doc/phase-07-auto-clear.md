# Phase 7: Auto-Clear Timer

**Objective:** Automatically clear old bot messages from chats to prevent clutter while keeping recent context.

## Architecture

```
Background Timer (every hour)
       │
       │ Check all chat sessions
       │ for auto_clear_enabled = 1
       │ AND last_activity > 24 hours ago
       ↓
┌─────────────────────────────────┐
│  Message Cleanup          │
│  - Delete bot messages      │
│  - Keep last 3 (config)    │
│  - Update last_activity      │
└─────────────────────────────────┘
```

## Core Components

### 1. Cleanup Manager (`cleanup_manager.py`)

```python
import asyncio
from datetime import datetime, timedelta
from typing import List, Set
from database import DatabaseManager
import logging

logger = logging.getLogger(__name__)

class CleanupManager:
    """Manage automatic chat message cleanup."""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.running = False
        self.task = None
        self.keep_messages = 3  # Keep last N messages
    
    async def check_and_clean_chats(self):
        """Check all chats for cleanup eligibility."""
        chats_to_clear = self.db.get_chats_to_clear(hours=24)
        
        if not chats_to_clear:
            logger.debug("No chats require cleanup")
            return
        
        logger.info(f"Found {len(chats_to_clear)} chats to clean")
        
        for chat_id in chats_to_clear:
            await self._cleanup_chat(chat_id)
    
    async def _cleanup_chat(self, chat_id: int):
        """Clean messages for a specific chat."""
        try:
            # Get bot's messages in chat
            messages = await get_bot_messages(chat_id)
            
            if not messages:
                logger.debug(f"No messages to clean for chat {chat_id}")
                return
            
            # Check if we have enough to keep
            if len(messages) <= self.keep_messages:
                logger.debug(f"Chat {chat_id} only has {len(messages)} messages, skipping")
                return
            
            # Delete all but last N messages
            to_delete = messages[:-self.keep_messages]  # Keep last N
            
            for msg_id in to_delete:
                await delete_bot_message(chat_id, msg_id)
                logger.debug(f"Deleted message {msg_id} from chat {chat_id}")
            
            # Update last_activity (prevents re-cleaning too soon)
            self.db.update_chat_activity(chat_id)
            
            logger.info(f"Cleaned {len(to_delete)} messages from chat {chat_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning chat {chat_id}: {e}")
    
    async def start(self, interval_minutes: int = 60):
        """Start background cleanup task."""
        if self.running:
            logger.warning("Cleanup manager already running")
            return
        
        self.running = True
        logger.info(f"Starting cleanup manager (checks every {interval_minutes} minutes)")
        
        while self.running:
            try:
                await self.check_and_clean_chats()
                await asyncio.sleep(interval_minutes * 60)  # Convert to seconds
            
            except asyncio.CancelledError:
                logger.info("Cleanup manager stopped")
                break
            except Exception as e:
                logger.error(f"Cleanup manager error: {e}")
                await asyncio.sleep(60)  # Wait before retry
    
    def stop(self):
        """Stop cleanup manager."""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("Cleanup manager stopped")
```

### 2. Bot Message Retrieval (`bot.py` additions)

```python
# Helper functions for message cleanup

async def get_bot_messages(chat_id: int, limit: int = 100) -> List[int]:
    """Get bot's message IDs from a chat."""
    # Using python-telegram-bot's get_chat_history
    # This requires the bot to have messages stored or fetched
    
    async with bot:
        messages = []
        async for msg in bot.get_chat_history(chat_id, limit=limit):
            # Check if message is from this bot
            if msg.from_user.id == bot.id:
                messages.append(msg.message_id)
        
        return messages

async def delete_bot_message(chat_id: int, message_id: int) -> bool:
    """Delete a specific bot message."""
    try:
        await bot.delete_message(chat_id, message_id)
        return True
    except Exception as e:
        logger.error(f"Failed to delete message {message_id}: {e}")
        return False
```

### 3. User Preferences (`database.py` additions)

```python
# Add to DatabaseManager class

def get_user_preference(self, user_id: int) -> Optional[Dict]:
    """Get user's auto-clear preferences."""
    with self.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_preferences WHERE user_id = ?
        """, (user_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None

def update_auto_clear(self, user_id: int, enabled: bool, hours: int = 24):
    """Update user's auto-clear settings."""
    with self.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_preferences 
            SET auto_clear_enabled = ?, auto_clear_hours = ?, updated_at = ?
            WHERE user_id = ?
        """, (enabled, hours, datetime.now().isoformat()))
        
        conn.commit()
```

### 4. Command Handler

```python
# In bot.py

async def handle_auto_clear(update: Update, context):
    """Handle /clear24h command."""
    args = context.args
    
    if not args:
        # Show current status
        user_id = update.effective_user.id
        pref = db.get_user_preference(user_id)
        
        if pref:
            status = "✅ ON" if pref['auto_clear_enabled'] else "❌ OFF"
            hours = pref.get('auto_clear_hours', 24)
            
            await update.message.reply_text(
                f"🕒 **Auto-Clear Settings:**\n\n"
                f"Status: {status}\n"
                f"Interval: {hours} hours\n\n"
                f"Usage: /clear24h <on|off> <hours>"
            )
        else:
            await update.message.reply_text(
                "Auto-clear is not configured.\n"
                "Usage: /clear24h <on|off> <hours>"
            )
        return
    
    # Parse command
    action = args[0].lower()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if action == 'on':
        # Get hours if specified, default to 24
        hours = int(args[1]) if len(args) > 1 else 24
        
        db.update_auto_clear(user_id, enabled=True, hours=hours)
        await update.message.reply_text(
            f"✅ Auto-clear enabled ({hours}h interval)"
        )
    
    elif action == 'off':
        db.update_auto_clear(user_id, enabled=False)
        await update.message.reply_text(
            "❌ Auto-clear disabled"
        )
    
    else:
        await update.message.reply_text(
            "Usage: /clear24h <on|off> <hours>"
        )
    
    db.log_activity(user_id, chat_id, 'auto_clear_changed', {'action': action})
```

## Configuration

```python
# config.py or environment variables
AUTO_CLEAN_CHECK_INTERVAL = int(os.getenv('AUTO_CLEAN_CHECK_INTERVAL_MINUTES', '60'))  # Check every hour
AUTO_CLEAR_DEFAULT_HOURS = int(os.getenv('AUTO_CLEAR_DEFAULT_HOURS', '24'))
KEEP_LAST_MESSAGES = int(os.getenv('KEEP_LAST_MESSAGES', '3'))  # Keep last 3 bot messages
```

## Implementation Tasks

- [ ] Create `cleanup_manager.py` with CleanupManager class
- [ ] Implement background task loop with interval
- [ ] Add `get_chats_to_clear()` method to DatabaseManager
- [ ] Add `get_bot_messages()` and `delete_bot_message()` helpers
- [ ] Add user preference management methods to DatabaseManager
- [ ] Implement `/clear24h` command handler
- [ ] Test cleanup logic with different keep_counts (1, 3, 5)
- [ ] Add cleanup logging and monitoring
- [ ] Integrate with main bot startup
- [ ] Handle edge cases (empty chats, rate limits)

## Notes

- **Granular Control:** Users can set per-hour intervals (6h, 12h, 24h, 48h)
- **Keep Context:** Last N messages preserved (prevents losing recent state)
- **Activity Tracking:** last_activity prevents re-cleaning same chat too soon
- **Performance:** Batch delete operations to respect rate limits
- **Safety:** Only deletes bot's own messages (never user messages)
