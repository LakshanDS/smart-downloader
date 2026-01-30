"""Shared utilities and state for Smart Downloader."""

from .state import db
from .auth import check_authorized, BotError, NotAuthorizedError
