# Cookie Management for Telegram Video Downloader

**Research Date:** January 29, 2026
**Status:** Planning Document - Approaches Analyzed

---

## Overview

This document analyzes approaches for managing authentication cookies in a Telegram bot that uses yt-dlp to download videos from sites requiring authentication (YouTube, Vimeo, etc.).

---

## Problem Statement

yt-dlp requires cookies to download from sites with:
- Age restrictions
- Login requirements
- Premium content
- Bot detection (YouTube, Vimeo)

**Challenge:** How to securely provide and manage cookies in a Telegram bot environment?

---

## Approaches Analyzed

### 1. User Uploads Cookie File (RECOMMENDED)

**Description:** User exports cookies from browser and uploads via Telegram

#### How It Works

1. User runs locally (one-time):
   ```bash
   yt-dlp --cookies-from-browser chrome --cookie-export cookies.txt
   ```

2. User sends `/upload_cookies` command to bot
3. Bot receives file, validates, encrypts, stores
4. yt-dlp uses stored cookies with `--cookies` flag

#### Implementation Example

```python
# handlers/cookies.py

from telegram import Update
from telegram.ext import ContextTypes
import os
from cryptography.fernet import Fernet

# Cookie storage directory
COOKIE_DIR = "cookies"
os.makedirs(COOKIE_DIR, exist_ok=True)

# Encryption (load from env or generate)
KEY = os.getenv('COOKIE_ENCRYPTION_KEY', Fernet.generate_key())
CIPHER = Fernet(KEY)

async def upload_cookies(update: Update, context: ContextTypes):
    """Handle cookie file upload from user."""

    if not update.message.document:
        await update.message.reply_text(
            "Please send a cookie.txt file.\n"
            "Generate it with:\n"
            "yt-dlp --cookies-from-browser chrome --cookie-export cookies.txt"
        )
        return

    # Download file
    document = update.message.document
    file = await document.get_file()

    temp_path = f"{COOKIE_DIR}/temp_{update.effective_user.id}.txt"
    await file.download_to_drive(temp_path)

    # Validate
    if not validate_cookie_file(temp_path):
        await update.message.reply_text("Invalid cookie file format")
        os.remove(temp_path)
        return

    # Encrypt and store
    encrypted = CIPHER.encrypt(open(temp_path, 'rb').read())
    final_path = f"{COOKIE_DIR}/{update.effective_user.id}.enc"
    with open(final_path, 'wb') as f:
        f.write(encrypted)

    os.remove(temp_path)

    await update.message.reply_text(
        "Cookies stored securely!\n"
        "They'll be used automatically for downloads."
    )

def validate_cookie_file(path):
    """Basic validation - check if it's a valid Netscape cookie file."""
    try:
        with open(path, 'r') as f:
            first_line = f.readline()
            return first_line.startswith('# Netscape HTTP Cookie File')
    except:
        return False

def get_decrypted_cookies(user_id):
    """Get decrypted cookie file path for yt-dlp."""
    encrypted_path = f"{COOKIE_DIR}/{user_id}.enc"

    if not os.path.exists(encrypted_path):
        return None

    # Decrypt to temp file
    decrypted = CIPHER.decrypt(open(encrypted_path, 'rb').read())
    temp_path = f"{COOKIE_DIR}/temp_{user_id}.txt"

    with open(temp_path, 'wb') as f:
        f.write(decrypted)

    return temp_path
```

#### Integration with Universal Downloader

```python
# In universal_downloader/direct_downloader.py

async def _download_yt_dlp(self, url, metadata, user_cookies=None, progress_callback=None):
    """Download using yt-dlp with optional cookies."""

    ydl_opts = {
        'outtmpl': output_template,
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
    }

    # Add cookies if available
    if user_cookies:
        ydl_opts['cookiefile'] = user_cookies

    # Rest of download logic...
```

| Aspect | Rating |
|--------|--------|
| **Complexity** | Low |
| **Reliability** | High |
| **Maintenance** | Low |
| **User Experience** | Medium (one-time setup) |

**Best For:** Personal bots, testing, small user bases

---

### 2. Browser Extension + Bot API

**Description:** Browser extension automatically pushes cookies to your bot API

#### How It Works

```javascript
// Browser extension (manifest v3)
// Background script
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tab.url.includes('youtube.com')) {
    chrome.cookies.getAll({url: tab.url}, (cookies) => {
      // Send to your bot API
      fetch('https://your-bot-api.com/cookies', {
        method: 'POST',
        body: JSON.stringify({
          user_id: getUserId(),
          cookies: cookies,
          domain: 'youtube.com'
        }),
        headers: {'Content-Type': 'application/json'}
      });
    });
  }
});
```

| Aspect | Rating |
|--------|--------|
| **Complexity** | High |
| **Reliability** | High |
| **Maintenance** | High |
| **User Experience** | High (automatic) |

**Best For:** Commercial services, large user bases

**Challenges:**
- Chrome Web Store review process
- Privacy concerns (users sending cookies to server)
- Extension maintenance overhead

---

### 3. Inline OAuth Login

**Description:** Bot opens inline keyboard for OAuth flow

#### How It Works

```python
# Inline keyboard for Google OAuth
keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Sign in with Google",
                          url=oauth_url)],
    [InlineKeyboardButton("Enter code manually",
                          callback_data="manual_code")]
])

await update.message.reply_text(
    "Sign in to enable YouTube downloads:",
    reply_markup=keyboard
)
```

#### Flow
1. User clicks "Sign in with Google"
2. Opens OAuth in browser
3. User authorizes
4. OAuth callback sends tokens to bot
5. Bot exchanges tokens for cookies

| Aspect | Rating |
|--------|--------|
| **Complexity** | Very High |
| **Reliability** | High |
| **Maintenance** | Medium |
| **User Experience** | Very High |

**Best For:** Production applications, multiple users

**Challenges:**
- OAuth app registration needed
- Google API quotas/costs
- Tokens ≠ cookies (may not work with all sites)

---

### 4. Headless Browser (NOT RECOMMENDED)

**Description:** Use Playwright/Selenium to navigate and extract cookies

#### Implementation Example

```python
from playwright.async_api import async_playwright

async def get_cookies_playwright(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ]
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)...',
            viewport={'width': 1920, 'height': 1080}
        )

        page = await context.new_page()
        await page.goto(url)
        await page.wait_for_url('*watch*')  # Wait for login

        cookies = await context.cookies()
        await browser.close()

        return cookies
```

#### Why NOT Recommended (2025 Reality)

| Issue | Reality |
|-------|---------|
| **Bot Detection** | YouTube, Vimeo actively detect headless browsers |
| **CAPTCHAs** | Increasingly sophisticated, require solving |
| **Arms Race** | Detection methods evolve faster than bypasses |
| **Maintenance** | Requires constant updates to stealth techniques |
| **Reliability** | Never 100% - breaks when sites update |

**Current State (2025):**
- [Stealthy Playwright packages](https://seleniumbase.com/stealthy-playwright-mode-bypass-captchas-and-bot-detection/) exist but aren't foolproof
- [Headful mode](https://www.scrapeless.com/en/blog/avoid-bot-detection-with-playwright-stealth) (visible browser) sometimes works
- [User agent rotation](https://blog.csdn.net/Instrustar/article/details/152654386) helps but isn't enough
- Detection methods are improving faster than bypasses

| Aspect | Rating |
|--------|--------|
| **Complexity** | Medium (implementation) / Very High (maintenance) |
| **Reliability** | Low |
| **Maintenance** | Very High |
| **User Experience** | Low (requires manual login) |

**When Might Work:** Educational projects, short-term testing, non-critical downloads

---

### 5. Telegram Mini Apps + SecureStorage

**Description:** Use Telegram's new Bot API 8.0 SecureStorage

Telegram Bot API 8.0 (November 2024) introduced [SecureStorage](https://core.telegram.org/bots/webapps) for Mini Apps.

```javascript
// In Telegram Mini App
if (Telegram.WebApp) {
  Telegram.WebApp.sendData({
    action: 'store_cookies',
    cookies: userCookies
  });
}
```

| Aspect | Rating |
|--------|--------|
| **Complexity** | Medium |
| **Reliability** | Medium |
| **Maintenance** | Low |
| **User Experience** | High |

**Best For:** Mobile-first users, privacy-focused applications

**Challenges:**
- Requires Mini App development
- Only works within Telegram client
- Server can't access stored data directly
- Newer tech (less documentation)

---

## Security Considerations (CRITICAL)

### Key Finding

**Telegram Bot communications are NOT end-to-end encrypted**

[Source: Stack Overflow](https://stackoverflow.com/questions/48150276/is-telegram-bot-communication-secured-via-end-to-end-encryption)

> E2E encryption in Telegram only applies to user chats, not bot communications.

You **MUST** implement your own encryption:

```python
from cryptography.fernet import Fernet
import os

class SecureCookieStorage:
    def __init__(self):
        # Generate or load encryption key
        self.key = os.environ.get('COOKIE_ENCRYPTION_KEY') or Fernet.generate_key()
        self.cipher = Fernet(self.key)

    def encrypt_cookies(self, cookie_file_path):
        with open(cookie_file_path, 'rb') as f:
            data = f.read()
        return self.cipher.encrypt(data)

    def decrypt_cookies(self, encrypted_data):
        return self.cipher.decrypt(encrypted_data)

    def store_cookies(self, user_id, cookie_file_path):
        encrypted = self.encrypt_cookies(cookie_file_path)
        # Store in database or filesystem
        db.save_user_cookies(user_id, encrypted)
```

### Security Checklist

| Requirement | Status |
|-------------|--------|
| Encrypt cookies at rest | Required |
| Use environment variables for keys | Required |
| Never log cookie contents | Required |
| Set file permissions (600) | Required |
| Per-user cookie isolation | Required |
| Implement cookie expiration | Recommended |
| Use HTTPS for all communications | Required |
| Remember: No E2E encryption | Critical |

---

## Comparison Summary

| Approach | Complexity | Best For | Maintenance | Reliability |
|----------|-----------|----------|-------------|-------------|
| **User Upload** | Low | Personal/Small bots | Low | High |
| **Browser Extension** | High | Commercial | High | High |
| **Inline OAuth** | Very High | Production | Medium | High |
| **Headless Browser** | Medium/High | Testing | Very High | Low |
| **Mini Apps** | Medium | Mobile privacy | Low | Medium |

---

## Recommendations

### For Smart Downloader Project

**Phase 1: Start with User Upload Approach**
- Easiest to implement
- Most reliable
- Works immediately
- You control the workflow

**Phase 2: Future Enhancement Options**
- Browser extension - for better UX if user base grows
- Mini Apps - if focusing on mobile users

**Phase 3: Avoid for Now**
- Headless browser (maintenance nightmare)
- OAuth (over-engineering for initial version)

---

## Implementation Plan

### Step 1: Create Cookie Handler Module

```python
# src/handlers/cookies.py
"""
Cookie management handler for Telegram bot.
"""

from telegram import Update
from telegram.ext import ContextTypes
import os
from cryptography.fernet import Fernet

COOKIE_DIR = "cookies"
KEY = os.getenv('COOKIE_ENCRYPTION_KEY')
CIPHER = Fernet(KEY) if KEY else None

async def cmd_upload_cookies(update: Update, context: ContextTypes):
    """Handle /upload_cookies command."""
    await update.message.reply_text(
        "Send your cookie.txt file.\n\n"
        "Generate it with:\n"
        "yt-dlp --cookies-from-browser chrome --cookie-export cookies.txt"
    )

async def handle_cookie_file(update: Update, context: ContextTypes):
    """Handle cookie file upload."""
    # Implementation from above
    pass

async def cmd_list_cookies(update: Update, context: ContextTypes):
    """List stored cookies for user."""
    pass

async def cmd_delete_cookies(update: Update, context: ContextTypes):
    """Delete stored cookies."""
    pass
```

### Step 2: Register Handlers

```python
# In bot.py
from handlers import cookies

application.add_handler(CommandHandler("upload_cookies", cookies.cmd_upload_cookies))
application.add_handler(MessageHandler(filters.Document.ALL, cookies.handle_cookie_file))
application.add_handler(CommandHandler("list_cookies", cookies.cmd_list_cookies))
application.add_handler(CommandHandler("delete_cookies", cookies.cmd_delete_cookies))
```

### Step 3: Update Universal Downloader

```python
# Pass cookies to yt-dlp when available
if user_cookies_path:
    ydl_opts['cookiefile'] = user_cookies_path
```

---

## Unresolved Questions

1. **Cookie expiration handling**
   - How to detect when cookies expire?
   - Prompt user to re-upload automatically?

2. **Multi-site support**
   - Separate cookies for each site (YouTube, Vimeo)?
   - Or try to use one file for all?

3. **Storage limits**
   - Telegram file upload limits
   - Database vs filesystem storage

4. **Backup strategy**
   - If cookies become invalid
   - Fallback or notification system?

5. **Shared cookies**
   - For family/team use
   - Should cookies be shareable between users?

---

## Additional Resources

### Libraries & Tools
- [python-telegram-bot](https://python-telegram-bot.readthedocs.io/) - Official Python Telegram bot library
- [cryptography](https://cryptography.io/) - Python encryption library
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloader

### Documentation
- [yt-dlp Cookie Extraction](https://github.com/yt-dlp/yt-dlp/issues/12040)
- [Telegram Bot API 8.0](https://core.telegram.org/bots/webapps)
- [Netscape Cookie Format](https://curl.se/rfc/cookie_spec.html)

### Research Sources
- [Stealthy Playwright Mode](https://seleniumbase.com/stealthy-playwright-mode-bypass-captchas-and-bot-detection/)
- [Playwright Bypass CAPTCHA](https://oxylabs.io/blog/playwright-bypass-captcha)
- [Headless Detection Bypass 2025](https://blog.csdn.net/Instrustar/article/details/152654386)
- [Telegram Security Discussion](https://stackoverflow.com/questions/48150276/is-telegram-bot-communication-secured-via-end-to-end-encryption)

---

## Decision Matrix

Use this to decide which approach fits your needs:

| Factor | User Upload | Extension | OAuth | Headless | Mini App |
|--------|-------------|-----------|-------|----------|----------|
| **Time to Implement** | 1-2 hours | 20+ hours | 40+ hours | 5-10 hours | 10+ hours |
| **Ongoing Maintenance** | Minimal | High | Medium | Very High | Low |
| **User Friction** | Medium | Low | Very Low | High | Low |
| **Privacy** | User controlled | Server stores | Server stores | Server stores | Local |
| **Reliability** | 95%+ | 95%+ | 90%+ | 60-80% | 85%+ |
| **Scalability** | Low | High | High | Low | Medium |

---

## Next Steps

**Option A: Quick Start**
1. Implement basic cookie upload handler
2. Test with real cookie file
3. Integrate with Universal Downloader
4. Iterate based on issues

**Option B: More Research**
1. Explore browser extension architecture
2. Research OAuth flows for YouTube
3. Look into Telegram Mini Apps examples

**Option C: Simplify**
1. Use public/non-premium content only
2. Skip authentication for MVP
3. Add cookies later if needed

---

**Document Version:** 1.0
**Last Updated:** January 29, 2026
