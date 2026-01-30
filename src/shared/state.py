"""Global state management."""

from database import DatabaseManager
from config import DATABASE_PATH

# Database instance
db = DatabaseManager(DATABASE_PATH)

# Pooler process instance (initialized at runtime)
pooler = None

# Queue manager instance (deprecated - replaced by pooler)
queue_manager = None

# Setup verification: {chat_id: {'code': '123456', 'user_id': 123, 'username': 'abc', 'message_id': 123}}
pending_verifications = {}

# Link submission mode: {chat_id: {'active': True/False}}
link_submission_mode = {}

# Userbot setup workflow: {chat_id: {'step': 1-5, 'api_id': ..., 'api_hash': ..., 'phone': ...}}
userbot_setup = {}

# Active Download Manager views: {chat_id: {'message_id': 123, 'task': asyncio_task}}
active_download_managers = {}
