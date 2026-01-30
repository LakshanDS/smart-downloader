"""Userbot setup handlers - interactive configuration wizard."""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, userbot_setup
from shared.auth import require_auth

logger = logging.getLogger(__name__)


@require_auth
async def handle_userbot_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /userbot_setup command - interactive userbot configuration."""
    chat_id = update.effective_chat.id

    logger.info(f"Starting userbot setup for chat_id={chat_id}")
    userbot_setup[chat_id] = {'step': 1}

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='userbot_cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🤖 *Userbot Setup Wizard*\n\n"
        "Guide to set up your Telegram userbot (supports file uploads up to 2GB).\n\n"
        "Before starting, make sure you have:\n\n"
        "1️⃣ *API ID*\n"
        "    *✤ Go to →* [my.telegram.org](https://my.telegram.org)\n"
        "    *✤ Login → API development tools*\n"
        "        *→ App title:* {Your App title}\n"
        "        *→ Short name:* {Your App short name}\n"
        "        *→ Platform:* Desktop\n\n"
        "    ✤ Copy the *App api_id*\n\n"
        "2️⃣ *API Hash*\n"
        "    ✤ From the same page\n"
        "    ✤ Copy the *App api_hash* (keep it secret)\n\n"
        "3️⃣ *Your phone number*\n"
        "    ✤ Include country code\n"
        "    ✤ Example: +94712345678\n\n"
        "When ready, *send your API ID* to continue.\n"
        "Send `Cancel` anytime to exit.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_userbot_setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle userbot setup button callbacks."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    if query.data == 'userbot_cancel':
        if chat_id in userbot_setup:
            del userbot_setup[chat_id]
        await query.edit_message_text("❌ Userbot setup cancelled.")
        return


async def handle_userbot_setup_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input during userbot setup workflow."""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    logger.debug(f"Userbot text handler called: chat_id={chat_id}, text='{text}', in_setup={chat_id in userbot_setup}")

    if chat_id not in userbot_setup:
        return

    step = userbot_setup[chat_id]['step']

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='userbot_cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if step == 1:
        if not text.isdigit() or len(text) < 5 or len(text) > 10:
            await update.message.reply_text(
                "❌ *Invalid API ID*\n\n"
                "API ID should be a number (5-10 digits).\n\n"
                "Please send your API ID:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        userbot_setup[chat_id]['api_id'] = int(text)
        userbot_setup[chat_id]['step'] = 2

        await update.message.reply_text(
            f"✅ API ID saved: `{text}`\n\n"
            f"Next, send your **API Hash** from my.telegram.org",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif step == 2:
        if len(text) < 20 or len(text) > 40:
            await update.message.reply_text(
                "❌ *Invalid API Hash*\n\n"
                "API Hash should be 32 characters long.\n\n"
                "Please send your API Hash:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        userbot_setup[chat_id]['api_hash'] = text
        userbot_setup[chat_id]['step'] = 3

        await update.message.reply_text(
            f"✅ API Hash saved\n\n"
            f"Next, send your **phone number** with country code.\n\n"
            f"Example: `+947712345678`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif step == 3:
        if not text.startswith('+'):
            await update.message.reply_text(
                "❌ *Invalid phone format*\n\n"
                "Phone number must start with `+` and country code.\n\n"
                "Example: `+947712345678`",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        if not text[1:].isdigit() or len(text) < 8:
            await update.message.reply_text(
                "❌ *Invalid phone format*\n\n"
                "Please include country code and number.\n\n"
                "Example: `+947712345678`",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        userbot_setup[chat_id]['phone'] = text
        userbot_setup[chat_id]['step'] = 4

        confirm_keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data='userbot_confirm')],
            [InlineKeyboardButton("❌ Cancel", callback_data='userbot_cancel')]
        ]
        confirm_markup = InlineKeyboardMarkup(confirm_keyboard)

        await update.message.reply_text(
            "📋 *Confirm Userbot Setup*\n\n"
            f"API ID: `{userbot_setup[chat_id]['api_id']}`\n"
            f"API Hash: `{userbot_setup[chat_id]['api_hash'][:10]}...`\n"
            f"Phone: `{userbot_setup[chat_id]['phone']}`\n\n"
            "Is this correct?",
            reply_markup=confirm_markup,
            parse_mode='Markdown'
        )

    elif step == 4:
        await update.message.reply_text(
            "Please use the buttons above to confirm or cancel."
        )


async def handle_userbot_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle userbot setup confirmation."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    if chat_id not in userbot_setup:
        await query.edit_message_text("❌ Setup session expired. Start again with /userbot_setup")
        return

    data = userbot_setup[chat_id]

    try:
        env_path = '.env'
        with open(env_path, 'r') as f:
            env_lines = f.readlines()

        updated_lines = []
        found_vars = {'UPLOADER_API_ID': False, 'UPLOADER_API_HASH': False, 'UPLOADER_PHONE': False}

        for line in env_lines:
            line = line.strip()
            if line.startswith('UPLOADER_API_ID='):
                updated_lines.append(f"UPLOADER_API_ID={data['api_id']}\n")
                found_vars['UPLOADER_API_ID'] = True
            elif line.startswith('UPLOADER_API_HASH='):
                updated_lines.append(f"UPLOADER_API_HASH={data['api_hash']}\n")
                found_vars['UPLOADER_API_HASH'] = True
            elif line.startswith('UPLOADER_PHONE='):
                updated_lines.append(f"UPLOADER_PHONE={data['phone']}\n")
                found_vars['UPLOADER_PHONE'] = True
            elif line and not line.startswith('#'):
                updated_lines.append(line + '\n')

        if not found_vars['UPLOADER_API_ID']:
            updated_lines.append(f"UPLOADER_API_ID={data['api_id']}\n")
        if not found_vars['UPLOADER_API_HASH']:
            updated_lines.append(f"UPLOADER_API_HASH={data['api_hash']}\n")
        if not found_vars['UPLOADER_PHONE']:
            updated_lines.append(f"UPLOADER_PHONE={data['phone']}\n")

        with open(env_path, 'w') as f:
            f.writelines(updated_lines)

        import config
        config.UPLOADER_API_ID = str(data['api_id'])
        config.UPLOADER_API_HASH = data['api_hash']
        config.UPLOADER_PHONE = data['phone']

        del userbot_setup[chat_id]

        await query.edit_message_text(
            "✅ *Userbot configured successfully!*\n\n"
            "Your bot can now upload files up to **2GB**.\n\n"
            "The bot will restart momentarily to apply changes...",
            parse_mode='Markdown'
        )

        logger.info(f"Userbot configured by user {chat_id}. Restart recommended.")

    except Exception as e:
        logger.error(f"Userbot setup failed: {e}")
        del userbot_setup[chat_id]
        await query.edit_message_text(
            f"❌ *Setup failed:*\n\n{str(e)}\n\n"
            f"Please try again with /userbot_setup",
            parse_mode='Markdown'
        )
