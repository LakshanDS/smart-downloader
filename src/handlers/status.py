"""Status handler - /status command."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from shared.state import db
from shared.auth import require_auth

logger = logging.getLogger(__name__)


@require_auth
async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active download status."""
    active = db.get_active_download()
    queue_summary = db.get_queue_summary()

    if not active:
        if queue_summary['pending'] == 0:
            await update.message.reply_text("✅ No active downloads")
        else:
            await update.message.reply_text(
                f"⏳ {queue_summary['pending']} items in queue.\n"
                f"Pooler will process them shortly..."
            )
        return

    progress = active['progress']
    dl_speed = active.get('download_speed', 0) or 0
    ul_speed = active.get('upload_speed', 0) or 0
    eta = active.get('eta_seconds', 0) or 0

    filled = int(20 * progress / 100)
    bar = '█' * filled + '░' * (20 - filled)

    dl_str = f"{dl_speed:.2f} MB/s" if dl_speed else "0.00 MB/s"
    ul_str = f"{ul_speed:.2f} MB/s" if ul_speed else "0.00 MB/s"

    if eta > 0:
        eta_mins = eta // 60
        eta_secs = eta % 60
        eta_str = f"{eta_mins}m {eta_secs}s"
    else:
        eta_str = "Calculating..."

    # Pooler status messages
    status_emoji = {
        'downloading': '📥',
        'uploading': '📤',
        'downloaded': '✅',
        'uploaded': '✅'
    }
    emoji = status_emoji.get(active['status'], '📋')

    message = f"""
{emoji} **Active Task:**

**Status:** {active['status'].title()}
**Title:** {active['title'] or 'Processing...'}
**Progress:** [{bar}] {progress}%

**Speed:**
↓ Download: {dl_str}
↑ Upload: {ul_str}

⏱️ ETA: {eta_str}

**Queue:** {queue_summary['pending']} pending
    """

    await update.message.reply_text(message, parse_mode='Markdown')
