# Bug Tracker

**Last Updated**: 2026-01-27
**Project**: Smart Downloader

---

## Active Bugs

| ID | Severity | Title | Status | Phase |
|----|----------|-------|--------|-------|
| None | - | - | - | - |

---

## Fixed Bugs

| ID | Severity | Title | Fixed | Phase |
|----|----------|-------|-------|-------|
| BUG-001 | High | Missing `mark_completed()` in DatabaseManager | ✅ 2026-01-27 | Phase 2 |
| BUG-002 | Low | yt-dlp domain check too limited | ✅ 2026-01-27 | Phase 2 |
| BUG-003 | Low | No URL validation in /download command | ✅ 2026-01-27 | Phase 2 |

---

## Bug Details

### BUG-001: Missing `mark_completed()` Method ✅ FIXED

**Severity**: High
**Status**: Fixed
**Phase**: Phase 2
**Found**: 2026-01-27
**Fixed**: 2026-01-27

**Description**:
`queue_manager.py` calls `self.db.mark_completed(download_id=download_id)` but this method doesn't exist in `database.py`.

**Location**:
- `src/queue_manager.py:105-108`
- `src/database.py` (missing method)

**Impact**:
When Phase 3 QueueManager tries to mark a download as completed, it will crash with AttributeError.

**Fix Applied**:
Added `mark_completed()` method to `queue_manager.py` that wraps the existing database method:
```python
async def mark_completed(self, download_id: int):
    """Mark download as completed."""
    self.db.update_download_status(download_id, 'completed')
    logger.info(f"Download completed: {download_id}")
```

---

### BUG-002: Limited yt-dlp Domain Support ✅ FIXED

**Severity**: Low
**Status**: Fixed
**Phase**: Phase 2
**Found**: 2026-01-27
**Fixed**: 2026-01-27

**Description**:
The `is_ytdlp_supported()` function only checks 4 domains (youtube.com, youtu.be, vimeo.com, dailymotion.com). yt-dlp actually supports 1000+ sites.

**Location**:
- `src/bot.py:261-264`

**Impact**:
Links from supported sites (e.g., Twitter, Reddit, TikTok) are incorrectly classified as 'crawler' instead of 'direct', causing them to be processed by Playwright instead of yt-dlp.

**Fix Applied**:
Removed domain check, now lets yt-dlp handle all HTTP/HTTPS URLs:
```python
def is_ytdlp_supported(url: str) -> bool:
    """Check if URL is supported by yt-dlp."""
    # yt-dlp supports 1000+ sites, let it handle all HTTP/HTTPS URLs
    return url.startswith(('http://', 'https://'))
```

---

### BUG-003: No URL Validation ✅ FIXED

**Severity**: Low
**Status**: Fixed
**Phase**: Phase 2
**Found**: 2026-01-27
**Fixed**: 2026-01-27

**Description**:
The `/download` command accepts any string without validation. No length limits, format checking, or sanitization.

**Location**:
- `src/bot.py:280-292` (handle_download)

**Impact**:
- Invalid URLs crash the source detection
- Extremely long URLs could cause database issues
- No user feedback for malformed URLs

**Fix Applied**:
Added validation in `handle_download()`:
```python
# Validate URL length
if len(url) > 2048:
    await update.message.reply_text("❌ URL too long (max 2048 characters)")
    return

# Validate URL format
try:
    result = urlparse(url)
    if not all([result.scheme, result.netloc]):
        raise ValueError("Invalid URL format")
except ValueError as e:
    await update.message.reply_text(f"❌ Invalid URL: {str(e)}")
    return
```

---

## Bug Submission Template

```markdown
### BUG-XXX: [Short Title]

**Severity**: Critical | High | Medium | Low
**Status**: Open | In Progress | Fixed | Closed
**Phase**: [Phase number]
**Found**: [YYYY-MM-DD]

**Description**:
[Detailed description of the bug]

**Location**:
- `path/to/file.py:line_number`

**Impact**:
[What happens because of this bug?]

**Fix**:
```python
# Code showing the fix
```

**Assigned To**: [Name]
**Target**: [Phase to fix in]
```
