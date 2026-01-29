"""Authorization and error handling."""

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
