# Smart Downloader - Main Plan

**Project Goal:** Build a Telegram-based personal media server using Telegram as storage (2 GB limit via userbot).

**Core Concept:**
- User sends download commands → Bot handles processing → Uploads via userbot → Forwards file to user
- No external storage needed (Telegram IS the storage)
- Modular architecture for maintainability and scalability

## Architecture Overview

```
User (@lakshan_desilva)
       │
       │ Commands: /torrent, /download, /movie, /tv, /porn, /myfiles
       ↓
┌────────────────────────────────────────────┐
│  @MediaServerBot (Main Bot - Bot API)   │
│  - 50 MB direct upload limit             │
│  - User interface (commands, inline UI)    │
└────────────────────────────────────────────┘
       │
       │ Routes downloads to:
       ├────────────────────────────────────────┤
       │                                  │
       │  Three parallel engines:            │
       │  ↓                                  │
       │  ┌──────────┬──────────┬──────────┐
       │  │          │          │          │
       │  ↓          ↓          ↓          ↓
       │  aria2c    Playwright  Category   Chat
       │  (torrents) (crawler)   Browser    Manager
       │                                  │
       │  All save to SQLite                 │
       │  ↓                                  │
       └──────────────────────────────────────┘
                  │
                  │ Uploads completed files
                  ↓
       ┌──────────────────────────────────────┐
       │  @UploaderBot (Userbot - User API) │
       │  - 2 GB upload limit                │
       │  - Stores to Telegram              │
       │  - Returns file_id to main bot       │
       └──────────────────────────────────────┘
                  │
                  │ Forwards file_id (any size!)
                  ↓
       ┌──────────────────────────────────────┐
       │  @MediaServerBot receives file_id  │
       │  - Forwards to user directly        │
       └──────────────────────────────────────┘
                  │
                  ↓
       User receives file, plays in Telegram app
```

## Key Features

1. **Multi-Source Downloads**
   - Torrent support (via aria2c)
   - Direct HTTP/HTTPS links
   - Unsupported sites (via Playwright crawler)
   - Automatic source detection

2. **Content Organization**
   - Categories: Movies, TV Shows, Porn, Custom
   - Browse by category with inline buttons
   - Search/filter within categories
   - Personal library view

3. **Smart Storage**
   - Telegram as backend (2 GB limit via userbot)
   - No external hosting costs
   - Native playback in Telegram app
   - File metadata tracking (size, duration, format)

4. **User Experience**
   - Real-time download progress
   - ETA and speed display
   - Auto-clear old chat messages (24h configurable)
   - Keyboard shortcuts and inline UI
   - Multi-queue support

## Tech Stack

**Backend:**
- Python 3.11+
- python-telegram-bot (main bot interface)
- Telethon/Pyrogram (uploader userbot)
- SQLite (database)
- aria2c (torrents via RPC)
- Playwright (headless browser crawler)

**Infrastructure:**
- Single browser instance (RAM optimization)
- Context pool for concurrent crawls
- Download queue manager
- Background task processing

## Development Phases

1. **Phase 1:** Database Design & Foundation
2. **Phase 2:** Core Bot Framework
3. **Phase 3:** Torrent Handler (aria2c)
4. **Phase 4:** Playwright Crawler
5. **Phase 5:** Userbot Uploader Integration
6. **Phase 6:** Category Browser & UI
7. **Phase 7:** Auto-Clear Timer
8. **Phase 8:** Polish & Optimization

## Design Principles

- **Modular:** Each component can be developed/tested independently
- **Scalable:** Easy to add new download sources or categories
- **Maintainable:** Clear separation of concerns
- **User-Centric:** Fast response times, intuitive interface

## Success Criteria

- ✅ Multiple users can download concurrently
- ✅ Supports torrents, direct links, and unsupported sites
- ✅ Files organized by category
- ✅ Auto-cleanup prevents chat clutter
- ✅ Works within Telegram's upload limits
- ✅ Clean, intuitive user experience

---

*This is the main source of truth. For detailed implementation, see individual phase documents.*
