"""Global state management."""

from database import DatabaseManager
from config import DATABASE_PATH

# Database instance
db = DatabaseManager(DATABASE_PATH)

# Queue manager instance (initialized at runtime)
queue_manager = None

# Setup verification: {chat_id: {'code': '123456', 'user_id': 123, 'username': 'abc', 'message_id': 123}}
pending_verifications = {}

# Link submission mode: {chat_id: {'active': True/False}}
link_submission_mode = {}

# Userbot setup workflow: {chat_id: {'step': 1-5, 'api_id': ..., 'api_hash': ..., 'phone': ...}}
userbot_setup = {}
