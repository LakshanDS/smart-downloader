"""Userbot setup handlers - interactive configuration wizard."""

import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from shared.state import db, userbot_setup
from shared.auth import require_auth

logger = logging.getLogger(__name__)

# Store pending auth codes: {chat_id: {'phone': str, 'code': str, 'phone_code_hash': str}}
pending_auth_codes = {}


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

    elif step == 5:
        # Handle verification code entry
        code = text.strip()

        if not code or len(code) < 3:
            await update.message.reply_text(
                "❌ *Invalid code*\n\n"
                "Please enter the verification code you received on Telegram.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        data = userbot_setup[chat_id]

        try:
            from telethon import TelegramClient
            from telethon.tl.functions.auth import SignInRequest

            session_name = f'sessions/{data["phone"]}'
            client = TelegramClient(session_name, data['api_id'], data['api_hash'])

            await client.connect()

            # Sign in with the code
            await client(SignInRequest(
                data['phone'],
                data.get('phone_code_hash', ''),
                code
            ))

            if await client.is_user_authorized():
                me = await client.get_me()
                await client.disconnect()

                del userbot_setup[chat_id]

                await update.message.reply_text(
                    f"✅ *Userbot configured successfully!*\n\n"
                    f"Logged in as: {me.first_name} (@{me.username or 'no username'})\n\n"
                    f"Your bot can now upload files up to **2GB**.\n\n"
                    f"Restart the bot to apply changes.",
                    parse_mode='Markdown'
                )

                logger.info(f"Userbot authenticated for {chat_id}: {me.first_name}")
            else:
                await client.disconnect()
                await update.message.reply_text(
                    "❌ *Authentication failed*\n\n"
                    "The code was incorrect or expired.\n\n"
                    "Please try again with /userbot_setup",
                    parse_mode='Markdown'
                )
                del userbot_setup[chat_id]

        except Exception as e:
            logger.error(f"Userbot sign in failed: {e}")
            del userbot_setup[chat_id]
            await update.message.reply_text(
                f"❌ *Authentication failed:*\n\n{str(e)}\n\n"
                f"Please try again with /userbot_setup",
                parse_mode='Markdown'
            )


async def handle_userbot_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle userbot setup confirmation and send auth code."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    if chat_id not in userbot_setup:
        await query.edit_message_text("❌ Setup session expired. Start again with /userbot_setup")
        return

    data = userbot_setup[chat_id]

    try:
        # Save to .env first
        env_path = '.env'
        with open(env_path, 'r') as f:
            env_lines = f.readlines()

        updated_lines = []
        found_vars = {'UPLOADER_API_ID': False, 'UPLOADER_API_HASH': False, 'UPLOADER_PHONE': False}

        for line in env_lines:
            line_stripped = line.strip()
            if line_stripped.startswith('UPLOADER_API_ID='):
                updated_lines.append(f"UPLOADER_API_ID={data['api_id']}\n")
                found_vars['UPLOADER_API_ID'] = True
            elif line_stripped.startswith('UPLOADER_API_HASH='):
                updated_lines.append(f"UPLOADER_API_HASH={data['api_hash']}\n")
                found_vars['UPLOADER_API_HASH'] = True
            elif line_stripped.startswith('UPLOADER_PHONE='):
                updated_lines.append(f"UPLOADER_PHONE={data['phone']}\n")
                found_vars['UPLOADER_PHONE'] = True
            elif line_stripped and not line_stripped.startswith('#'):
                updated_lines.append(line if line.endswith('\n') else line + '\n')

        if not found_vars['UPLOADER_API_ID']:
            updated_lines.append(f"UPLOADER_API_ID={data['api_id']}\n")
        if not found_vars['UPLOADER_API_HASH']:
            updated_lines.append(f"UPLOADER_API_HASH={data['api_hash']}\n")
        if not found_vars['UPLOADER_PHONE']:
            updated_lines.append(f"UPLOADER_PHONE={data['phone']}\n")

        with open(env_path, 'w') as f:
            f.writelines(updated_lines)

        # Now send the authentication code
        from telethon import TelegramClient

        session_name = f'sessions/{data["phone"]}'
        os.makedirs('sessions', exist_ok=True)

        client = TelegramClient(session_name, data['api_id'], data['api_hash'])

        await query.edit_message_text(
            "📱 *Sending verification code...*\n\n"
            "Please wait...",
            parse_mode='Markdown'
        )

        # Connect and send code
        await client.connect()

        if await client.is_user_authorized():
            await client.disconnect()
            await query.edit_message_text(
                "✅ *Userbot already authenticated!*\n\n"
                "Your bot can now upload files up to **2GB**.\n\n"
                "Restart the bot to apply changes.",
                parse_mode='Markdown'
            )
            del userbot_setup[chat_id]
            return

        # Send code request
        from telethon.tl.functions.auth import SendCodeRequest
        result = await client(SendCodeRequest(data['phone'], 5, 'sms' if '+881' not in data['phone'] else 'app'))

        # Store for verification
        userbot_setup[chat_id]['phone_code_hash'] = result.phone_code_hash
        userbot_setup[chat_id]['step'] = 5  # Now waiting for code

        await client.disconnect()

        await query.edit_message_text(
            "✅ *Verification code sent!*\n\n"
            f"Check your Telegram for the code sent to `{data['phone']}`\n\n"
            "Send the code here to complete setup.",
            parse_mode='Markdown'
        )

        logger.info(f"Auth code sent to {data['phone']} for user {chat_id}")

    except Exception as e:
        logger.error(f"Userbot auth failed: {e}")
        del userbot_setup[chat_id]
        await query.edit_message_text(
            f"❌ *Authentication failed:*\n\n{str(e)}\n\n"
            f"Please try again with /userbot_setup",
            parse_mode='Markdown'
        )
