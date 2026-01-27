# Changelog

All notable changes to Smart Downloader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-01-27

### Features
- **Telegram Bot Integration**: Full bot framework with python-telegram-bot
- **Setup Wizard**: One-time `/setup` command locks bot to your account
- **Owner Authorization**: All commands protected with owner lock checks
- **Command Routing**: `/start`, `/help`, `/status`, `/download`, `/torrent` implemented
- **Source Detection**: Auto-detects torrent, direct (yt-dlp), and crawler links
- **Queue Placeholder**: QueueManager stub for Phase 3 compatibility
- **Error Handling**: Global error handler with user-friendly messages
- **Environment Configuration**: dotenv support for secure credential management

### Improvements
- **Type Safety**: Custom exception classes (BotError, NotAuthorizedError, InvalidURLError, FileTooLargeError)
- **Logging**: Structured logging with configurable levels
- **Modular Design**: Separate config.py for environment variables
- **Markdown Messages**: Formatted messages with emoji and progress bars
- **yt-dlp Support**: Now supports all 1000+ yt-dlp sites (removed domain whitelist)

### Fixes
- **BUG-001**: Added `mark_completed()` method to QueueManager
- **BUG-002**: Removed yt-dlp domain whitelist, now supports all HTTP/HTTPS URLs
- **BUG-003**: Added URL validation (length limit 2048, format checking)

### Breaking Changes
- No breaking changes

### Security
- Owner lock enforced on all commands
- Non-owners receive rejection message
- Bot token required via environment variable

### Known Issues
- QueueManager is placeholder (full implementation in Phase 3)
- No unit tests for bot module (manual testing required)

---

## [0.1.0] - 2026-01-27

### Features
- **Database Foundation**: Implemented SQLite-based storage for all application data
- **Owner Lock System**: Single-user security ensures only you can use your personal bot
- **Download Queue**: FIFO queue management for sequential download processing
- **Media Library**: Full-featured media storage with metadata tracking
- **Full-Text Search**: Fast search across your entire media library
- **Categories**: Organize content into Movies, TV Shows, Porn, or Custom categories
- **Favorites/Watch Later**: Mark items for quick access later
- **Activity Logging**: Track all actions for debugging and auditing

### Improvements
- **No External Dependencies**: Database uses only Python standard library
- **Automatic Setup**: Tables and indexes created on first run
- **Default Categories**: Pre-seeded with common content types

### Fixes
- No fixes yet

### Breaking Changes
- No breaking changes

### Security
- Owner lock prevents unauthorized access to your personal bot
- All database operations use parameterized queries (SQL injection safe)

### Known Issues
- Database migration system not yet implemented (manual DB deletion needed for schema changes)
- WAL mode not enabled (may affect concurrent read/write performance)

---

## [Unreleased]

### Features
- No new features yet

### Improvements
- No improvements yet

### Fixes
- No fixes yet

### Breaking Changes
- No breaking changes
