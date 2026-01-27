# Phase 5: Direct Download Handler (yt-dlp)

**Objective:** Handle direct HTTP/HTTPS downloads and yt-dlp supported sites with metadata-first file size validation.

## Architecture

```
Queue Manager calls handler
       │
       ↓ Detect if yt-dlp supports URL
       ↓
┌────────────────────────────────────┐
│  Metadata Extraction (First!)     │
│  - yt-dlp --skip-download         │
│  - Get file size, title, duration  │
│  - Validate < 2GB                  │
└────────────────────────────────────┘
       │
       ↓ If valid
┌────────────────────────────────────┐
│  Download                          │
│  - yt-dlp with progress hook       │
│  - Update DB every 5s              │
│  - Handle errors                   │
└────────────────────────────────────┘
```

## Key Features

- **Metadata-first**: Extract file size before downloading
- **File size validation**: Reject files >2GB before download starts
- **Progress tracking**: Real-time speed and ETA updates
- **yt-dlp integration**: Support for YouTube, Vimeo, and 1000+ sites
- **Fallback**: Can also handle direct HTTP/HTTPS links

## Components

### 1. Direct Download Handler (`direct_handler.py`)

```python
import asyncio
import logging
import subprocess
import json
from typing import Dict, Optional
from database import DatabaseManager
import os

logger = logging.getLogger(__name__)

class DirectHandler:
    """Handle direct downloads via yt-dlp."""

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.download_dir = '/tmp/downloads'

    async def get_metadata(self, url: str) -> Dict:
        """Extract metadata without downloading."""
        logger.info(f"Extracting metadata for: {url}")

        try:
            # Use yt-dlp to get metadata
            cmd = [
                'yt-dlp',
                '--skip-download',
                '--dump-json',
                url
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"Metadata extraction failed: {error_msg}")
                raise ValueError(f"Could not extract metadata: {error_msg[:100]}")

            # Parse JSON output
            metadata = json.loads(stdout.decode())

            return {
                'title': metadata.get('title', 'Unknown'),
                'duration': metadata.get('duration'),
                'filesize': metadata.get('filesize'),
                'uploader': metadata.get('uploader'),
                'thumbnail': metadata.get('thumbnail'),
                'description': metadata.get('description'),
                'url': url
            }

        except Exception as e:
            logger.error(f"Metadata extraction error: {e}")
            raise

    def validate_file_size(self, metadata: Dict) -> bool:
        """Check if file is under 2GB limit."""
        file_size = metadata.get('filesize')

        if file_size is None:
            # Could not determine size, allow it but warn
            logger.warning("Could not determine file size, proceeding anyway")
            return True

        if file_size > self.MAX_FILE_SIZE:
            logger.warning(f"File too large: {file_size} bytes")
            return False

        return True

    async def download(self, url: str, download_id: int) -> str:
        """Download file with progress tracking."""
        # First, get metadata
        metadata = await self.get_metadata(url)

        # Validate file size
        if not self.validate_file_size(metadata):
            file_size_gb = metadata.get('filesize', 0) / (1024 ** 3)
            raise ValueError(
                f"File too large: {file_size_gb:.2f} GB "
                f"(Telegram limit: 2 GB)"
            )

        # Update download info in DB
        self.db.update_download_status(
            download_id,
            'downloading'
        )

        logger.info(f"Starting download: {metadata['title']}")

        # Create download directory
        os.makedirs(self.download_dir, exist_ok=True)

        # Download template
        output_template = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        # Progress callback
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)

                if total > 0:
                    progress = int(downloaded / total * 100)
                else:
                    progress = 0

                # Update database
                self.db.update_progress(
                    download_id,
                    progress=progress,
                    download_speed=speed / (1024 * 1024) if speed else 0,  # MB/s
                    eta_seconds=eta
                )

        # yt-dlp configuration
        ydl_opts = {
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'nocookies': True,
            'nocheckcertificate': True,
        }

        # Download using yt-dlp Python API
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find downloaded file
            filename = ydl.prepare_filename(metadata)

            if not os.path.exists(filename):
                # Try alternative extension
                base = os.path.splitext(filename)[0]
                for ext in ['.mp4', '.webm', '.mkv', '.mp3']:
                    alt_path = base + ext
                    if os.path.exists(alt_path):
                        filename = alt_path
                        break

            logger.info(f"Download complete: {filename}")

            # Mark as complete
            self.db.update_progress(
                download_id,
                progress=100,
                download_speed=0,
                eta_seconds=0
            )

            return filename

        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise


# For direct HTTP/HTTPS links (not yt-dlp supported)
class DirectHTTPHandler:
    """Handle direct HTTP/HTTPS downloads."""

    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def get_file_info(self, url: str) -> Dict:
        """Get file info via HEAD request."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True) as response:
                content_length = response.headers.get('Content-Length')
                content_type = response.headers.get('Content-Type', '')

                # Try to get filename from URL
                filename = url.split('/')[-1]
                if '.' not in filename:
                    filename = 'download'

                return {
                    'filesize': int(content_length) if content_length else None,
                    'filename': filename,
                    'content_type': content_type,
                    'url': url
                }

    async def download(self, url: str, download_id: int) -> str:
        """Download file with progress tracking."""
        import aiohttp

        # Get file info first
        info = await self.get_file_info(url)

        # Validate size
        if info['filesize'] and info['filesize'] > self.MAX_FILE_SIZE:
            size_gb = info['filesize'] / (1024 ** 3)
            raise ValueError(f"File too large: {size_gb:.2f} GB")

        # Start download
        output_path = f'/tmp/downloads/{info["filename"]}'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0

                with open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total > 0:
                            progress = int(downloaded / total * 100)
                        else:
                            progress = 0

                        # Update progress
                        self.db.update_progress(
                            download_id,
                            progress=progress,
                            download_speed=len(chunk) / (1024 * 1024),  # Rough estimate
                            eta_seconds=0
                        )

        return output_path
```

### 2. Integration with Queue Manager

```python
# In queue_manager.py

elif source == 'direct':
    from direct_handler import DirectHandler

    # First, get metadata
    handler = DirectHandler(self.db)
    metadata = await handler.get_metadata(url)

    # Update title in database
    self.db.update_download_status(
        download_id, 'downloading'
    )

    # Download
    file_path = await handler.download(url, download_id)
```

## Configuration

```python
# config.py
YTDLP_FORMAT = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
DOWNLOAD_DIR = '/tmp/downloads'
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
```

## Implementation Tasks

- [ ] Install yt-dlp and yt-dlp-python
- [ ] Create `direct_handler.py` with DirectHandler class
- [ ] Implement metadata extraction (--skip-download)
- [ ] Add file size validation (<2GB)
- [ ] Implement download with progress hook
- [ ] Add DirectHTTPHandler for direct links
- [ ] Update database progress every 5 seconds
- [ ] Test with various yt-dlp supported sites
- [ ] Test with direct HTTP links
- [ ] Handle error cases (404, connection timeout)

## Dependencies

```python
# requirements.txt additions
yt-dlp>=2023.0.0
aiohttp>=3.8.0
```

## Notes

- **Metadata-first**: Always check size before downloading
- **Progress hook**: yt-dlp's built-in progress tracking
- **Fallback**: DirectHTTPHandler for non-yt-dlp links
- **File size**: Reject >2GB before download starts
- **Title extraction**: Get proper filename from metadata
