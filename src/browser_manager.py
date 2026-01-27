"""
Browser Manager - Smart Downloader

Phase 6: Playwright Crawler - Browser Management
Manages Playwright browser instance and context pool for RAM optimization.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Browser Manager - Playwright Integration

    Manage Playwright browser instance and context pool.
    Single browser instance with multiple contexts for RAM optimization.
    """

    def __init__(self, headless: bool = True):
        """Initialize browser manager."""
        self.browser = None
        self.contexts: Dict[int, Any] = {}  # Chat ID -> context
        self.headless = headless
        self.playwright = None

    def _initialize_browser(self):
        """Launch browser once and reuse."""
        if self.browser is not None:
            return

        try:
            from playwright.sync_api import sync_playwright

            self.playwright = sync_playwright().start()

            # Launch browser with RAM optimization
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-dev-shm-usage',  # Reduce RAM
                    '--disable-software-rasterizer',
                    '--no-sandbox',  # If running as root
                ]
            )

            logger.info("Playwright browser launched")

        except ImportError:
            logger.error("Playwright not installed")
            raise RuntimeError(
                "Playwright not installed. "
                "Install with: pip install playwright && playwright install chromium"
            )
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise RuntimeError(f"Browser launch failed: {str(e)}")

    def get_context(self, chat_id: int):
        """
        Get or create context for a chat.

        Args:
            chat_id: User's chat ID

        Returns:
            Browser context
        """
        self._initialize_browser()

        if chat_id not in self.contexts:
            self.contexts[chat_id] = self.browser.new_context()
            logger.info(f"Created context for chat {chat_id}")

        return self.contexts[chat_id]

    def cleanup_context(self, chat_id: int):
        """
        Close context when done.

        Args:
            chat_id: User's chat ID
        """
        if chat_id in self.contexts:
            self.contexts[chat_id].close()
            del self.contexts[chat_id]
            logger.info(f"Cleaned up context for chat {chat_id}")

    def cleanup_all(self):
        """Close all contexts and browser."""
        for context in self.contexts.values():
            try:
                context.close()
            except Exception as e:
                logger.warning(f"Error closing context: {e}")

        self.contexts.clear()

        if self.browser:
            try:
                self.browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self.browser = None

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
            finally:
                self.playwright = None

        logger.info("Browser cleanup complete")

    def __del__(self):
        """Cleanup on object deletion."""
        self.cleanup_all()
