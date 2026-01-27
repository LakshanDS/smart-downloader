# Smart Downloader

A Telegram-based personal media server using Telegram as storage (2 GB per-file limit via userbot).

## Overview

Smart Downloader is a personal bot that allows you to download content from multiple sources (torrents, direct downloads, and crawled content) and store them directly in Telegram.

### Key Features

- **Multi-source downloads:** Torrents (aria2c), HTTP/HTTPS (yt-dlp), Unsupported sites (Playwright)
- **Queue management:** Process downloads one-at-a-time with progress tracking
- **Smart storage:** Telegram as unlimited storage backend
- **Content organization:** Categories, favorites, search, and watch later
- **Single-user:** Personal bot locked to your chat ID

## Installation

```bash
git clone https://github.com/LakshanDS/smart-downloader.git
cd smart-downloader
pip install -r requirements.txt
```

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get your bot token
3. Run the setup wizard to configure your bot

## Usage

```
/download <URL>    - Download from URL
/torrent <URL>     - Download torrent
/myfiles           - Browse your library
/search <query>    - Search your downloads
/favorites         - View favorites
```

## Development

See [doc/main-plan.md](doc/main-plan.md) for the full development roadmap.

## License

MIT
