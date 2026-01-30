"""Authorization and error handling."""

from functools import wraps
from typing import Callable
from telegram import Update
from telegram.ext import ContextTypes

from .state import db


class BotError(Exception):
    """Base exception for bot errors."""
    pass


class NotAuthorizedError(BotError):
    """Raised when non-owner tries to use bot."""
    pass


class InvalidURLError(BotError):
    """Raised when URL is invalid."""
    pass


class FileTooLargeError(BotError):
    """Raised when file exceeds 2GB limit."""
    pass


def check_authorized(chat_id: int) -> bool:
    """Check if chat_id is authorized (owner)."""
    return db.is_authorized(chat_id)


async def handle_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unauthorized access uniformly."""
    if update.callback_query:
        await update.callback_query.edit_message_text("❌ You are not authorized to use this bot.")
    elif update.message:
        await update.message.reply_text(
            "❌ This bot is locked to another account.\n"
            "You cannot use it."
        )


def require_auth(func: Callable) -> Callable:
    """Decorator to require authorization for handler functions.

    Automatically checks auth and handles unauthorized access.
    Works with both message handlers and callback query handlers.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.effective_chat.id

        if not check_authorized(chat_id):
            await handle_unauthorized(update, context)
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
