"""Setup wizard handlers - initial bot configuration."""

import asyncio
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, pending_verifications

logger = logging.getLogger(__name__)


def generate_verification_code() -> str:
    """Generate 6-digit verification code."""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username

    # Check if bot is locked
    if not db.is_locked():
        keyboard = [[InlineKeyboardButton("🔐 Setup Bot", callback_data='setup_initiate')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = await update.message.reply_text(
            "🔐 *Setup Required*\n\n"
            "This bot needs to be locked to your account first.\n"
            "Click the button below to start setup.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        pending_verifications[chat_id] = {
            'start_message_id': msg.message_id,
            'code': None,
            'user_id': None,
            'username': None,
            'message_id': None
        }
        return

    # Check authorization
    from shared.auth import check_authorized
    if not check_authorized(chat_id):
        await update.message.reply_text(
            "❌ This bot is already locked to another account.\n"
            "You cannot use it."
        )
        return

    # Update chat activity
    db.log_activity(user_id, chat_id, 'bot_start')

    from handlers.dashboard import show_main_dashboard
    await show_main_dashboard(update, context)


async def handle_setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle setup button callback."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username

    # Delete the initial /start message if exists
    start_msg_id = None
    if chat_id in pending_verifications and pending_verifications[chat_id].get('start_message_id'):
        start_msg_id = pending_verifications[chat_id]['start_message_id']
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=start_msg_id)
        except Exception:
            pass

    code = generate_verification_code()

    print(f"\n{'='*50}")
    print(f"🔐 SETUP VERIFICATION CODE")
    print(f"{'='*50}")
    print(f"User: @{username or 'N/A'} (ID: {user_id})")
    print(f"Chat ID: {chat_id}")
    print(f"\n📲 Verification Code: {code}")
    print(f"{'='*50}\n")

    logger.info(f"Setup initiated by @{username or 'N/A'} (ID: {user_id}) - Code: {code}")

    verification_msg = await update.effective_chat.send_message(
        f"🔐 *Verification Required*\n\n"
        f"A 6-digit code has been displayed in the terminal.\n\n"
        f"Send the code here to verify ownership and complete setup.\n\n"
        f"_Code expires in 10 minutes._",
        parse_mode='Markdown'
    )

    pending_verifications[chat_id] = {
        'code': code,
        'user_id': user_id,
        'username': username,
        'message_id': verification_msg.message_id
    }


async def handle_verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verification code from user."""
    chat_id = update.effective_chat.id

    if chat_id not in pending_verifications:
        return

    user_input = update.message.text.strip()

    if not user_input.isdigit() or len(user_input) != 6:
        await update.message.reply_text(
            "❌ Invalid format. Send the 6-digit code shown in terminal."
        )
        return

    pending = pending_verifications[chat_id]

    if user_input == pending['code']:
        try:
            db.set_owner(chat_id, pending['user_id'], pending['username'])
            logger.info(f"✅ Bot locked to @{pending['username'] or 'N/A'} (ID: {pending['user_id']})")

            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=pending['message_id'])
            except Exception:
                pass

            try:
                await update.message.delete()
            except Exception:
                pass

            del pending_verifications[chat_id]

            from handlers.dashboard import show_main_dashboard
            await update.message.reply_text(
                "✅ Setup complete! Restarting bot will start the pooler.\n\n"
                "Use /start to see the dashboard.",
                parse_mode='Markdown'
            )

            # Note: Pooler will start on next bot restart via bot.py startup_pooler()
            logger.info("Setup complete. Restart bot to start pooler process.")

        except Exception as e:
            logger.error(f"Setup failed: {e}")
            await update.message.reply_text(f"❌ Setup failed: {str(e)}")
    else:
        await update.message.reply_text(
            f"❌ Wrong code. Please try again.\n\n"
            f"Check the terminal for the correct 6-digit code."
        )


async def handle_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setup command (redirects to button flow)."""
    chat_id = update.effective_chat.id

    if db.is_locked():
        owner = db.get_owner()
        if owner['chat_id'] == chat_id:
            await update.message.reply_text(
                "✅ Bot is already set up and locked to your account!\n\n"
                "Use /start to see available commands."
            )
        else:
            await update.message.reply_text(
                "❌ This bot is already locked to another account."
            )
        return

    keyboard = [[InlineKeyboardButton("🔐 Setup Bot", callback_data='setup_initiate')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔐 *Bot Setup*\n\n"
        "Click the button below to start the setup process.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
