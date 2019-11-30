"""
Managing Telegram sticker packs and stickers using the bot interface.
"""
import logging

import telegram

logger = logging.getLogger('rubus')


def stickers_manage(update, context):  # pylint: disable=unused-argument
    """Present the user all available configuration options"""
    keyboard = [[telegram.InlineKeyboardButton("Create new sticker pack", callback_data='stickers_pack_new')]]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select configuration option:", reply_markup=reply_markup)


def stickers_manage_response(update, context):  # pylint: disable=unused-argument
    """Perform actions based on user response to stickers_manage keyboard"""
    query = update.callback_query
    query.edit_message_text(text=f"Selected option: {query.data}")
