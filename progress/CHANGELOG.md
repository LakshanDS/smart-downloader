# Changelog

All notable changes to Smart Downloader will be documented in this file.

## [Unreleased]

### [UNCOMMITTED] - 2026-01-28

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

#### Fixed
- **BUG-003**: Windows console encoding in test output (non-ASCII characters)

#### Known issue
- Category encoding fix is local to `tests/test_database.py` - should be moved to conftest.py or pytest.ini
- **BUG-001**: Phase 3-4 tests blocked by missing `python-telegram-bot` dependency
- **BUG-002**: Phase 5-6 tests blocked by TELEGRAM_BOT_TOKEN environment variable requirement
- **BUG-003**: UnicodeEncodeError in test output on Windows (partial fix in test_database.py only)
- **BUG-004**: "File too large" warning during Phase 5-6 test execution

---
