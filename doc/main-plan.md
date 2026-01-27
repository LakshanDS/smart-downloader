# Smart Downloader - Main Plan

**Project Goal:** Build a Telegram-based personal media server using Telegram as storage (2 GB per-file limit via userbot).

**Core Concept:**
- User sends download commands → Bot validates → Queues to database → Processes one-at-a-time → Uploads via userbot → Forwards file to user
- No external storage needed (Telegram IS the storage - unlimited)
- Single-user personal bot with setup lock

## Architecture Overview

```
User (Private Chat Only)
       │
       │ Commands: /torrent, /download, /movie, /tv, /porn, /myfiles, /search, /favorites
       ↓
┌────────────────────────────────────────────┐
│  @MediaServerBot (Main Bot - Bot API)   │
│  - 50 MB direct upload limit             │
│  - User interface (commands, inline UI)    │
│  - Queue manager (one-at-a-time)          │
│  - Progress tracking (edit messages)       │
└────────────────────────────────────────────┘
       │
       │ Routes to download engine:
       ↓
┌────────────────────────────────────────────┐
│         Download Queue Manager            │
│  - SQLite-based queue (progress=false)    │
│  - One download at a time                 │
│  - Auto-retry (3x: immediate, 2min, 10min)│
│  - File size validation (<2GB)            │
└────────────────────────────────────────────┘
       │
       │ Three parallel engines:
       ├──────────┬──────────────┬──────────────┤
       │          │              │              │
       ↓          ↓              ↓              ↓
    aria2c    yt-dlp        Playwright    Category
    (torrents) (direct)      (crawler)     Browser
       │          │              │              │
       └──────────┴──────────────┴──────────────┘
                  │
                  │ Save to SQLite (metadata only)
                  ↓
       ┌──────────────────────────────────────┐
       │  @UploaderBot (Userbot - User API) │
       │  - 2 GB per-file upload limit       │
       │  - Stores to "Saved Messages"       │
       │  - Returns file_id to main bot       │
       │  - Session file auth (no expiry)     │
       └──────────────────────────────────────┘
                  │
                  │ Forwards file_id (any size!)
                  ↓
       ┌──────────────────────────────────────┐
       │  @MediaServerBot receives file_id  │
       │  - Forwards to user directly        │
       │  - Updates DB (progress=true)        │
       │  - Deletes progress message (60s)    │
       └──────────────────────────────────────┘
                  │
                  ↓
       User receives file, plays in Telegram app
```

## Key Features

### 1. Download Management
- **Multi-source support:** Torrents (aria2c), HTTP/HTTPS (yt-dlp), Unsupported sites (Playwright)
- **Queue system:** Accept multiple links → process sequentially one-at-a-time
- **Pre-validation:** Check file size <2GB before downloading
- **Auto-retry:** 3 attempts with exponential backoff (immediate → 2min → 8min)
- **Progress tracking:** Real-time updates via message editing

### 2. Content Organization
- **Categories:** Movies, TV Shows, Porn, Custom
- **Browse by category:** Inline keyboard navigation
- **Local search:** Search SQLite DB by title, tags, ID (fast indexed)
- **Favorites/Watch Later:** Mark items for quick access
- **Duplicate detection:** Hash-based deduplication

### 3. Smart Storage
- **Telegram as backend:** Unlimited storage, 2GB per-file limit
- **No external hosting:** Zero hosting costs
- **Native playback:** Plays directly in Telegram app
- **File metadata:** Size, duration, format, download date

### 4. User Experience
- **Progress display:** Message editing (not pinning - not supported in 1:1)
- **Progress bar:** Visual percentage indicator
- **Auto-cleanup:** Delete progress messages 60s after completion
- **Queue visibility:** See pending/active downloads
- **Keyboard shortcuts:** Inline UI for all actions

### 5. Single-User Security
- **Setup lock:** Bot requires owner chat ID on first run
- **Outsider rejection:** All non-owner users ignored
- **Session-based auth:** Userbot uses session file (no expiry)

## Tech Stack

**Backend:**
- Python 3.11+
- python-telegram-bot 21.0+ (main bot interface)
- Telethon or Pyrogram (uploader userbot)
- SQLite (database + full-text search)
- aria2c with XML-RPC (torrents)
- yt-dlp (direct downloads)
- Playwright (headless browser crawler)

**Infrastructure:**
- Single browser instance (RAM optimization)
- Context pool for concurrent crawls
- Sequential download queue (one-at-a-time)
- Background task processing

## Development Phases

### Phase 1: Foundation & Database
- [ ] Database schema (owner lock, queue, media, favorites)
- [ ] Owner lock system (single-user)
- [ ] Queue operations (FIFO, one-at-a-time)
- [ ] Full-text search (media titles)
- [ ] Favorites/Watch Later support

### Phase 2: Core Bot Framework
- [ ] Bot skeleton with setup wizard
- [ ] Owner chat ID lock
- [ ] Command routing (/start, /setup, /download, /torrent, /status)
- [ ] Owner authorization checks
- [ ] Error handling

### Phase 3: Queue Manager
- [ ] Sequential queue processing (one-at-a-time)
- [ ] Progress tracking (5s intervals)
- [ ] Progress message display (single summary)
- [ ] Exponential backoff retry (0s → 2min → 8min)
- [ ] File size validation (<2GB)
- [ ] Oversized file notification

### Phase 4: Torrent Handler
- [ ] aria2c integration (torrents)
- [ ] Metadata extraction (file size before download)
- [ ] Progress tracking integration
- [ ] Error handling and retry

### Phase 5: Direct Download Handler
- [ ] yt-dlp integration
- [ ] Metadata-first validation (file size, title)
- [ ] Progress tracking
- [ ] Direct HTTP/HTTPS fallback
- [ ] 1000+ site support

### Phase 6: Playwright Crawler
- [ ] Browser manager (single instance)
- [ ] Network monitor (video URL capture)
- [ ] Video detector (ad filtering)
- [ ] File size validation
- [ ] Unsupported sites fallback

### Phase 7: Userbot Uploader
- [ ] Session-based authentication
- [ ] Upload to Telegram (2GB limit)
- [ ] Upload retry with exponential backoff
- [ ] Progress tracking
- [ ] File ID retrieval
- [ ] Forward to user

### Phase 8: Content Organization
- [ ] Category system (Movies, TV, Porn, Custom)
- [ ] Category browser (inline UI)
- [ ] Local search (SQLite FTS)
- [ ] Favorites/Watch Later
- [ ] /myfiles, /search, /favorites commands
- [ ] Duplicate detection

### Phase 9: Monitoring & Recovery
- [ ] Health check endpoint
- [ ] aria2c watchdog (auto-restart)
- [ ] Userbot connection monitor (auto-reconnect)
- [ ] Disk space monitoring
- [ ] Error notifications
- [ ] Auto-recovery

### Phase 10: Polish & Documentation
- [ ] Error message refinement
- [ ] Help documentation
- [ ] Deployment guide
- [ ] Performance optimization

## Design Principles

- **Single-user:** Personal bot, locked to one chat ID
- **Sequential processing:** One download at a time
- **Reliable first:** Auto-retry, health monitoring
- **Clean UX:** Progress bars, auto-cleanup, inline UI
- **Modular:** Each component independent

## Success Criteria

- ✅ Downloads multiple sources (torrent, direct, crawled)
- ✅ Processes queue one-at-a-time
- ✅ Validates file size before download
- ✅ Auto-retries failed downloads (3x)
- ✅ Uploads to Telegram via userbot (2GB limit)
- ✅ Real-time progress via message editing
- ✅ Search works on local SQLite DB
- ✅ Favorites/Watch Later functionality
- ✅ Owner-only access (outsiders rejected)
- ✅ Health monitoring + auto-recovery

## Database Schema (Simplified)

```sql
-- Media library (completed downloads)
CREATE TABLE media (
    id INTEGER PRIMARY KEY,
    file_id TEXT UNIQUE,           -- Telegram file ID
    title TEXT,
    category TEXT,
    file_size INTEGER,
    duration INTEGER,
    download_date TIMESTAMP,
    hash TEXT,                     -- For deduplication
    is_favorite BOOLEAN DEFAULT 0
);

-- Download queue (pending + active)
CREATE TABLE downloads (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    source TEXT,                   -- 'torrent', 'direct', 'crawler'
    status TEXT,                   -- 'pending', 'downloading', 'uploading', 'completed', 'failed'
    progress INTEGER DEFAULT 0,    -- 0-100
    retry_count INTEGER DEFAULT 0,
    added_date TIMESTAMP,
    error_message TEXT,
    file_size INTEGER,             -- Pre-validated size (bytes)
    title TEXT,                    -- Extracted from metadata
    download_speed REAL,           -- Current speed (MB/s)
    upload_speed REAL,             -- Current upload speed (MB/s)
    eta_seconds INTEGER            -- Estimated time remaining
);

-- User preferences
CREATE TABLE preferences (
    chat_id INTEGER PRIMARY KEY,   -- Owner only
    auto_clear_hours INTEGER,
    default_category TEXT
);
```

## Progress Display Flow

```
User sends: /download https://example.com/video.mp4
       ↓
Bot deletes user message
       ↓
Bot sends: "📥 Active Downloads:
━━━━━━━━━━━━━━━━━━━━━
Items in queue: 5

Downloading 1/5:
📹 My Awesome Video.mp4
[||||||||||    ] 80% (800 MB / 1 GB)
⏱️ ETA: 4m 32s
↓ 2.14 MB/s | ↑ 0.00 MB/s"
       ↓
Bot edits message every 5 seconds:
"📥 Active Downloads:
━━━━━━━━━━━━━━━━━━━━━
Items in queue: 5

Downloading 1/5:
📹 My Awesome Video.mp4
[||||||||||||  ] 95% (950 MB / 1 GB)
⏱️ ETA: 0m 24s
↓ 2.31 MB/s | ↑ 0.00 MB/s"
       ↓
Download complete, upload starts:
"📥 Active Downloads:
━━━━━━━━━━━━━━━━━━━━━
Items in queue: 5

Uploading 1/5:
📹 My Awesome Video.mp4
[||||||        ] 40% (400 MB / 1 GB)
⏱️ ETA: 3m 12s
↓ 0.00 MB/s | ↑ 1.78 MB/s"
       ↓
Upload complete:
"✅ Download complete: My Awesome Video.mp4
🎬 Ready to play!

[Deleting this message in 60s...]"
       ↓
Wait 60 seconds → Delete message
       ↓
Process next item in queue
```

## File Size Validation Flow

```
User sends: /download <URL>
       ↓
Bot fetches metadata first (without full download):
  • Torrent: Download .torrent metadata only
  • Direct: HEAD request for Content-Length
  • Playwright: Intercept video URL, check size
       ↓
Validate size < 2GB:
  ✅ Under 2GB → Proceed with download
  ❌ Over 2GB → Create DB entry, inform user, skip
       ↓
If over limit:
"⚠️ File too large:
📹 Huge Movie.mp4 (4.2 GB)
↳ Telegram limit: 2 GB per file

Skipped. Added to library for reference."
```

---

*This is the main source of truth. For detailed implementation, see individual phase documents.*
