# Phase 4: Playwright Crawler

**Objective:** Headless browser automation to download from unsupported sites (e.g., eporner.com) and find real video URLs.

## Architecture

```
Bot Command (download <url>)
       │
       │ Check if yt-dlp supports
       │
       ├──────────────┬──────────────┐
       │              │              │
       ↓              ↓              ↓
   Supported      Unsupported    Browser
   Sites          Sites         Manager
(yt-dlp)       │              │
                 │              │
                 │              │
                 │  Single instance (RAM optimization)
                 │  ┌────────┬────────┐
                 │  │        │        │
                 ↓          ↓        ↓
              Page Load   Network   Video
                         Monitor  Detector
```

## Core Components

### 1. Browser Manager (`browser_manager.py`)

```python
from playwright.sync_api import sync_playwright
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class BrowserManager:
    """Manage Playwright browser instance and context pool."""
    
    def __init__(self):
        self.browser = None
        self.contexts: Dict[int, Any] = {}  # Chat ID -> context
        self._initialize_browser()
    
    def _initialize_browser(self):
        """Launch browser once and reuse."""
        if self.browser is None:
            try:
                self.browser = sync_playwright().chromium.launch(
                    headless=True,
                    args=[
                        '--disable-dev-shm-usage',  # Reduce RAM
                        '--disable-software-rasterizer',
                        '--no-sandbox',  # If running as root
                    ]
                )
                logger.info("Playwright browser launched")
            except Exception as e:
                logger.error(f"Failed to launch browser: {e}")
                raise RuntimeError(f"Browser launch failed: {str(e)}")
    
    def get_context(self, chat_id: int):
        """Get or create context for a chat."""
        if chat_id not in self.contexts:
            self.contexts[chat_id] = self.browser.new_context()
            logger.info(f"Created context for chat {chat_id}")
        
        return self.contexts[chat_id]
    
    def cleanup_context(self, chat_id: int):
        """Close context when done."""
        if chat_id in self.contexts:
            self.contexts[chat_id].close()
            del self.contexts[chat_id]
            logger.info(f"Cleaned up context for chat {chat_id}")
    
    def cleanup_all(self):
        """Close all contexts and browser."""
        for context in self.contexts.values():
            context.close()
        
        if self.browser:
            self.browser.close()
        
        logger.info("Browser cleanup complete")
```

### 2. Video URL Detector (`video_detector.py`)

```python
from typing import List, Dict, Optional
import urllib.parse
import logging

logger = logging.getLogger(__name__)

class VideoDetector:
    """Identify real videos from potential candidates (ads, previews, etc.)."""
    
    def __init__(self):
        self.ad_keywords = ['ad', 'advertisement', 'promo', 'preview', 'teaser']
        self.min_duration = 30  # Seconds - minimum to not be an ad
        self.min_size = 1024 * 500  # 500 KB minimum
    
    def filter_videos(self, candidates: List[Dict]) -> Optional[Dict]:
        """Filter candidates to find the real video."""
        if not candidates:
            return None
        
        valid_videos = []
        
        for candidate in candidates:
            # Check content type
            if not self._is_video(candidate):
                continue
            
            # Check if it's likely an ad
            if self._is_likely_ad(candidate):
                logger.info(f"Filtered out likely ad: {candidate['url']}")
                continue
            
            valid_videos.append(candidate)
        
        if not valid_videos:
            return None
        
        # Return the largest/longest (usually the real video)
        return sorted(valid_videos, 
                   key=lambda x: (x.get('duration', 0), x.get('size', 0)),
                   reverse=True)[0]
    
    def _is_video(self, candidate: Dict) -> bool:
        """Check if URL appears to be a video."""
        content_type = candidate.get('content-type', '')
        
        video_types = ['video/mp4', 'video/webm', 'video/ogg', 'video/x-matroska']
        return any(vt in content_type.lower() for vt in video_types)
    
    def _is_likely_ad(self, candidate: Dict) -> bool:
        """Check for ad indicators."""
        # Check URL for ad keywords
        url = candidate['url'].lower()
        if any(keyword in url for keyword in self.ad_keywords):
            return True
        
        # Check for suspiciously small files
        size = candidate.get('size', 0)
        if size < self.min_size:
            return True
        
        # Duration check (if available)
        duration = candidate.get('duration', 0)
        if duration > 0 and duration < self.min_duration:
            return True
        
        return False
```

### 3. Network Monitor (`network_monitor.py`)

```python
from typing import List, Set, Callable
import logging

logger = logging.getLogger(__name__)

class NetworkMonitor:
    """Capture all video URLs from network requests."""
    
    def __init__(self):
        self.video_urls: Set[str] = set()
        self.candidates: List[Dict] = []
    
    def capture_urls(self) -> Callable:
        """Return a callback for Playwright response handler."""
        
        def on_response(response):
            content_type = response.headers.get('content-type', '')
            url = response.url
            
            # Only care about video responses
            if 'video' not in content_type.lower():
                return
            
            self.video_urls.add(url)
            self.candidates.append({
                'url': url,
                'content-type': content_type,
                'status': response.status,
                'headers': dict(response.headers)
            })
            
            logger.debug(f"Captured video URL: {url}")
        
        return on_response
    
    def get_candidates(self) -> List[Dict]:
        """Return all captured video URLs."""
        return self.candidates
    
    def reset(self):
        """Clear captured URLs."""
        self.video_urls.clear()
        self.candidates.clear()
```

### 4. Crawler (`playwright_crawler.py`)

```python
import asyncio
import hashlib
from typing import Optional, Dict
from browser_manager import BrowserManager
from network_monitor import NetworkMonitor
from video_detector import VideoDetector
import logging

logger = logging.getLogger(__name__)

class PlaywrightCrawler:
    """Headless browser crawler for unsupported sites."""
    
    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self.detector = VideoDetector()
        self.monitor = NetworkMonitor()
    
    async def find_video_url(self, url: str, chat_id: int) -> Optional[Dict]:
        """Find the real video URL from a page."""
        context = self.browser.get_context(chat_id)
        page = context.new_page()
        
        try:
            # Set up network monitoring
            monitor_callback = self.monitor.capture_urls()
            page.on('response', monitor_callback)
            
            # Navigate to page
            logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for video player to load
            await self._wait_for_video_player(page)
            
            # Wait a bit more for network requests
            await asyncio.sleep(3)
            
            # Get all captured URLs
            candidates = self.monitor.get_candidates()
            
            if not candidates:
                logger.warning(f"No video URLs captured from {url}")
                return None
            
            logger.info(f"Found {len(candidates)} video URL candidates")
            
            # Filter to find real video
            real_video = self.detector.filter_videos(candidates)
            
            if real_video:
                logger.info(f"Selected real video: {real_video['url']}")
                
                # Add metadata if we can get it
                real_video['source_url'] = url
                real_video['method'] = 'playwright'
                
                return real_video
            else:
                logger.warning(f"No valid video found from candidates")
                return None
        
        except Exception as e:
            logger.error(f"Crawler error for {url}: {e}")
            raise DownloadError(f"Failed to crawl page: {str(e)}")
        
        finally:
            self.monitor.reset()
            self.browser.cleanup_context(chat_id)
    
    async def _wait_for_video_player(self, page) -> None:
        """Wait for video player to appear."""
        selectors = [
            'video',
            '.video-player',
            '.player',
            '.video-container',
            '[role="main"]',
            'iframe[src*="video"]',
            '[id*="player"]',
        ]
        
        for selector in selectors:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                logger.debug(f"Found video player with selector: {selector}")
                return
            except:
                continue
        
        # Wait a bit for dynamic content
        await asyncio.sleep(2)
    
    def probe_video(self, url: str) -> Dict:
        """Download small sample to detect metadata."""
        # (Implementation in Phase 4 detail)
        # Uses HEAD request or small download
        pass
```

### 5. Integration with Bot

```python
# In bot.py
from playwright_crawler import PlaywrightCrawler
from browser_manager import BrowserManager

# Initialize
browser_manager = BrowserManager()
crawler = PlaywrightCrawler(browser_manager)

async def handle_download(update: Update, context):
    """Handle /download command."""
    url = args[0]
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_id = update.message.message_id
    
    # Check if yt-dlp supports it first
    if is_ytdlp_supported(url):
        # Route to yt-dlp handler (Phase 4 covers both)
        await handle_ytdlp_download(update, context)
        return
    
    # Fall back to Playwright
    await update.message.reply_text("🔍 Crawling page... (this may take 30-60 seconds)")
    
    try:
        video_info = await crawler.find_video_url(url, chat_id)
        
        if not video_info:
            await update.message.reply_text("❌ No video found. This site may not be supported.")
            return
        
        # Add to download queue
        gid = db.add_download(
            gid=f"pw_{hashlib.md5(video_info['url'].encode()).hexdigest()[:16]}",
            source_url=video_info['url'],
            source_type='unsupported',
            chat_id=chat_id,
            message_id=message_id
        )
        
        await update.message.reply_text(
            f"✅ Found video! Added to queue.\n\n"
            f"**URL:** {video_info['url'][:60]}..."
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
```

## RAM Optimization

```python
# Single browser instance
browser = p.chromium.launch(headless=True)

# Contexts per chat (not full browser instances)
context1 = browser.new_context()
context2 = browser.new_context()

# Each context is ~50-100 MB
# Can handle ~10-15 concurrent crawls on 1.9 GB RAM

# Cleanup when done
context.close()  # Frees ~50-100 MB
```

## Implementation Tasks

- [ ] Install Playwright and browsers
- [ ] Create `browser_manager.py` with BrowserManager class
- [ ] Create `video_detector.py` with ad filtering logic
- [ ] Create `network_monitor.py` for URL capture
- [ ] Create `playwright_crawler.py` main crawler
- [ ] Implement network request interception
- [ ] Add video player detection logic
- [ ] Implement real video selection algorithm
- [ ] Add error handling and timeouts
- [ ] Test with sample unsupported sites
- [ ] RAM usage testing (single browser + multiple contexts)

## Dependencies

```python
# requirements.txt additions
playwright>=1.40.0
```

## Browser Installation

```bash
# Install Playwright
pip install playwright

# Install browsers
playwright install chromium

# Verify
playwright --version
```

## Notes

- **Single Browser:** Reuse one browser instance to save RAM
- **Context Per Chat:** Isolated but shares browser resources
- **Ad Detection:** Filter based on duration, size, URL patterns
- **Timeouts:** 30-60 second wait times for page loads
- **Error Handling:** Graceful fallback when video not found
