"""
Tests for Phase 9: Category Manager & File Browser
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from category_manager import CategoryManager, FileBrowser, SearchHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


class TestCategoryManager:
    """Test cases for CategoryManager."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = Mock()
        db.get_all_categories = Mock()
        db.get_media_by_category = Mock()
        db.create_category = Mock()
        db.delete_category = Mock()
        db.rename_category = Mock()
        db.get_media_categories = Mock()
        db.add_media_to_category = Mock()
        db.remove_media_from_category = Mock()
        return db

    @pytest.fixture
    def category_manager(self, mock_db):
        """Create category manager instance."""
        return CategoryManager(mock_db)

    @pytest.fixture
    def mock_update(self):
        """Create mock update."""
        update = Mock(spec=Update)
        update.message = Mock()
        update.message.reply_text = AsyncMock()
        update.callback_query = Mock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.data = None
        update.callback_query.edit_message_text = AsyncMock()
        return update

    @pytest.fixture
    def mock_context(self):
        """Create mock context."""
        context = Mock(spec=ContextTypes)
        context.args = []
        return context

    def test_init(self, mock_db):
        """Test category manager initialization."""
        manager = CategoryManager(mock_db)
        assert manager.db == mock_db

    @pytest.mark.asyncio
    async def test_list_categories_empty(self, category_manager, mock_update, mock_context):
        """Test listing categories when none exist."""
        category_manager.db.get_all_categories.return_value = []

        await category_manager.list_categories(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "No categories yet" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_categories_success(self, category_manager, mock_update, mock_context):
        """Test successful category listing."""
        categories = [
            {'id': 1, 'name': 'Action', 'emoji': '🎬'},
            {'id': 2, 'name': 'Comedy', 'emoji': '😂'},
        ]
        category_manager.db.get_all_categories.return_value = categories
        category_manager.db.get_media_by_category.side_effect = [[], []]

        await category_manager.list_categories(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        message = mock_update.message.reply_text.call_args[0][0]
        assert "My Categories" in message

    @pytest.mark.asyncio
    async def test_create_category_success(self, category_manager, mock_update, mock_context):
        """Test successful category creation."""
        mock_context.args = ['Action', '🎬']
        category_manager.db.create_category.return_value = 1

        await category_manager.create_category(mock_update, mock_context)

        category_manager.db.create_category.assert_called_once_with('Action', '🎬')
        assert "Category created" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_category_no_args(self, category_manager, mock_update, mock_context):
        """Test category creation without arguments."""
        await category_manager.create_category(mock_update, mock_context)

        assert "Usage:" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_category_duplicate(self, category_manager, mock_update, mock_context):
        """Test creating duplicate category."""
        mock_context.args = ['Action', '🎬']
        category_manager.db.create_category.side_effect = Exception("UNIQUE")

        await category_manager.create_category(mock_update, mock_context)

        assert "already exists" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_delete_category_success(self, category_manager, mock_update, mock_context):
        """Test successful category deletion."""
        mock_context.args = ['Action']
        category_manager.db.get_all_categories.return_value = [{'id': 1, 'name': 'Action'}]

        await category_manager.delete_category(mock_update, mock_context)

        category_manager.db.delete_category.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_delete_category_not_found(self, category_manager, mock_update, mock_context):
        """Test deleting non-existent category."""
        mock_context.args = ['NonExistent']
        category_manager.db.get_all_categories.return_value = []

        await category_manager.delete_category(mock_update, mock_context)

        assert "not found" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rename_category_success(self, category_manager, mock_update, mock_context):
        """Test successful category rename."""
        mock_context.args = ['Action', 'Drama']
        category_manager.db.get_all_categories.return_value = [{'id': 1, 'name': 'Action'}]

        await category_manager.rename_category(mock_update, mock_context)

        category_manager.db.rename_category.assert_called_once_with(1, 'Drama')

    @pytest.mark.asyncio
    async def test_show_add_category_keyboard(self, category_manager, mock_update):
        """Test showing category selection keyboard."""
        categories = [
            {'id': 1, 'name': 'Action', 'emoji': '🎬'},
            {'id': 2, 'name': 'Comedy', 'emoji': '😂'},
        ]
        category_manager.db.get_all_categories.return_value = categories
        category_manager.db.get_media_categories.return_value = []

        await category_manager.show_add_category_keyboard(123, mock_update)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert call_args[1]['reply_markup'] is not None

    @pytest.mark.asyncio
    async def test_handle_callback_toggle(self, category_manager, mock_update, mock_context):
        """Test handling toggle callback."""
        mock_update.callback_query.data = 'addcat_123_1'
        category_manager.db.get_media_categories.return_value = []
        category_manager.db.add_media_to_category = Mock()
        category_manager.db.remove_media_from_category = Mock()

        await category_manager.handle_callback(mock_update, mock_context)

        # Verify the callback was answered
        mock_update.callback_query.answer.assert_called_once()


class TestFileBrowser:
    """Test cases for FileBrowser."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = Mock()
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = Mock(return_value=conn)
        conn.__exit__ = Mock(return_value=False)
        db.get_connection.return_value = conn
        return db

    @pytest.fixture
    def file_browser(self, mock_db):
        """Create file browser instance."""
        return FileBrowser(mock_db)

    @pytest.fixture
    def mock_update(self):
        """Create mock update."""
        update = Mock(spec=Update)
        update.message = Mock()
        update.message.reply_text = AsyncMock()
        return update

    def test_init(self, mock_db):
        """Test file browser initialization."""
        browser = FileBrowser(mock_db)
        assert browser.db == mock_db
        assert browser.ITEMS_PER_PAGE == 10

    @pytest.mark.asyncio
    async def test_show_all_files_empty(self, file_browser, mock_update):
        """Test showing files when none exist."""
        file_browser.db.get_connection.return_value.cursor.return_value.fetchall.return_value = []

        await file_browser.show_all_files(mock_update, page=1)

        assert "No files yet" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_show_all_files_success(self, file_browser, mock_update):
        """Test successful file listing."""
        mock_items = [
            {'id': 1, 'title': 'Movie 1', 'file_size': 1024000, 'is_favorite': False, 'created_at': '2026-01-27'},
        ]
        file_browser.db.get_connection.return_value.cursor.return_value.fetchall.return_value = mock_items

        await file_browser.show_all_files(mock_update, page=1)

        mock_update.message.reply_text.assert_called_once()
        message = mock_update.message.reply_text.call_args[0][0]
        assert "My Files" in message


class TestSearchHandler:
    """Test cases for SearchHandler."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = Mock()
        db.search_media = Mock()
        db.get_favorites = Mock()
        return db

    @pytest.fixture
    def search_handler(self, mock_db):
        """Create search handler instance."""
        return SearchHandler(mock_db)

    @pytest.fixture
    def mock_update(self):
        """Create mock update."""
        update = Mock(spec=Update)
        update.message = Mock()
        update.message.reply_text = AsyncMock()
        return update

    @pytest.fixture
    def mock_context(self):
        """Create mock context."""
        context = Mock(spec=ContextTypes)
        context.args = []
        return context

    def test_init(self, mock_db):
        """Test search handler initialization."""
        handler = SearchHandler(mock_db)
        assert handler.db == mock_db

    @pytest.mark.asyncio
    async def test_handle_search_no_args(self, search_handler, mock_update, mock_context):
        """Test search without query."""
        await search_handler.handle_search(mock_update, mock_context)

        assert "Usage:" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_search_no_results(self, search_handler, mock_update, mock_context):
        """Test search with no results."""
        mock_context.args = ['test']
        search_handler.db.search_media.return_value = []

        await search_handler.handle_search(mock_update, mock_context)

        assert "No results" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_search_success(self, search_handler, mock_update, mock_context):
        """Test successful search."""
        mock_context.args = ['action']
        search_handler.db.search_media.return_value = [
            {'id': 1, 'title': 'Action Movie'},
        ]

        await search_handler.handle_search(mock_update, mock_context)

        assert "Search Results" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_favorites_empty(self, search_handler, mock_update):
        """Test favorites when none exist."""
        search_handler.db.get_favorites.return_value = []

        await search_handler.handle_favorites(mock_update)

        assert "No favorites yet" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_favorites_success(self, search_handler, mock_update):
        """Test successful favorites listing."""
        search_handler.db.get_favorites.return_value = [
            {'id': 1, 'title': 'Favorite Movie'},
        ]

        await search_handler.handle_favorites(mock_update)

        assert "My Favorites" in mock_update.message.reply_text.call_args[0][0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
