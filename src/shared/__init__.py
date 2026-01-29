"""Shared utilities and state for Smart Downloader."""

from .state import db, queue_manager
from .auth import check_authorized, BotError, NotAuthorizedError
