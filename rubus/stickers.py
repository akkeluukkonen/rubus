"""
Managing Telegram sticker sets and stickers using the bot interface.
"""
import logging

import telegram

logger = logging.getLogger('rubus')

DEFAULT_STICKER_SET_PNG = "rubus/data/sticker_default.png"
DEFAULT_STICKER_SET_EMOJI = '\U0000267B'  # recycling symbol


def manage(update, context):  # pylint: disable=unused-argument
    """Present the user all available configuration options"""
    keyboard = [[telegram.InlineKeyboardButton("Create new sticker set", callback_data='set_new')]]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select configuration option:", reply_markup=reply_markup)


def manage_response(update, context):  # pylint: disable=unused-argument
    """Perform actions based on user response to manage stickers"""
    query = update.callback_query

    if query.data == 'set_new':
        _sticker_set_create_new(query)


def _sticker_set_create_new(query):
    user = query.from_user
    bot = query.bot.bot
    sticker_set_name = f"{user['username']}_by_{bot['username']}"

    try:
        with open(DEFAULT_STICKER_SET_PNG, 'rb') as png_sticker:
            success = query.bot.create_new_sticker_set(
                user['id'],
                sticker_set_name,
                sticker_set_name,  # Use the name also as the title for now
                png_sticker,
                DEFAULT_STICKER_SET_EMOJI)
    except telegram.error.BadRequest:
        logger.exception("Failed unexpectedly!")
        success = False

    if success:
        query.edit_message_text(text=f"Created a new sticker set named: {sticker_set_name}")
    else:
        query.edit_message_text(text="Failed to create the sticker set!")
