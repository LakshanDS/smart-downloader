# Changelog

All notable changes to Smart Downloader will be documented in this file.

## [Unreleased]

### [3175ee6] - 2026-01-28

#### Added
- Phase 7: Auto-clear timer (`src/cleanup_manager.py`) - Background chat message cleanup
- Phase 8: Userbot uploader (`src/uploader_bot.py`, `src/upload_manager.py`) - 2GB file upload support
- Phase 9: Content organization (`src/category_manager.py`) - Categories, file browser, search, favorites
- Phase 10: Health monitor (`src/health_monitor.py`) - Service monitoring and auto-recovery
- Test files: `test_phase07.py`, `test_phase08.py`, `test_phase09.py`, `test_phase10.py`
- `pytest.ini` - pytest configuration with asyncio_mode = auto

#### Changed
- `tests/conftest.py` - Added pytest-asyncio plugin configuration

#### Fixed
- **BUG-006**: pytest-asyncio configuration - added `pytest_plugins = ('pytest_asyncio',)` to conftest.py
- **BUG-007**: Missing `telethon` dependency - installed via `pip install -r requirements.txt`

#### Known issue
- `_get_bot_messages()` and `_delete_bot_message()` are stubs requiring bot client integration
- Linux-specific subprocess commands (`pkill`, `/tmp/downloads`)

---

### [00f123d] - 2026-01-28

#### Added
- `src/config_test.py` - Mock configuration for test isolation

#### Changed
- File size validation: changed from `>` to `>=` in `direct_handler.py` and `queue_manager.py` (now properly rejects files at exact MAX_FILE_SIZE limit)
- Test expectations: updated category count from 4 to 3 in `tests/test_database.py`

#### Fixed
- **BUG-002**: Config validation blocking tests - added `config_test.py` with mock values
- **BUG-003**: UnicodeEncodeError on Windows - added UTF-8 wrapper to `tests/test_database.py`
- **BUG-004**: File size check inconsistency - changed `>` to `>=` for proper boundary handling

#### Known issue
- Windows pytest crash ignored (Linux deployment target)

---

### [f5c7850] - 2026-01-27

#### Changed
- Category schema: migrated from 4 fixed categories (movie, tv, porn, custom) to 3 flexible categories (Favorites, Watch Later, Music)
- Database API: `add_media()` no longer accepts category parameter; use `add_media_to_category()` for many-to-many relationships
- Test encoding: added Windows UTF-8 stdout/stderr wrapper for test runner

#### Fixed
- Windows console encoding in test output (non-ASCII characters)

---
