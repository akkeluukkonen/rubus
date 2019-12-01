"""
Managing Telegram sticker sets and stickers using the bot interface.
"""
import enum
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler
from telegram.error import BadRequest

logger = logging.getLogger('rubus')

DEFAULT_STICKER_SET_PNG = "rubus/data/sticker_default.png"
DEFAULT_STICKER_SET_EMOJI = '\U0000267B'  # recycling symbol


class State(enum.Enum):
    """States for the ConversationHandler"""
    MENU = enum.auto()
    CREATE_SET = enum.auto()


def start(update, context):  # pylint: disable=unused-argument
    """Present the user all available configuration options"""
    keyboard = [
        [InlineKeyboardButton("Create new sticker set", callback_data=str(State.CREATE_SET))],
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select configuration option:", reply_markup=reply_markup)
    return State.MENU


def create_set(update, context):
    """Create a new sticker set, which is tied to the calling user

    The bot can manipulate this sticker set as it is the "co-creator" in this case.
    """
    user = update.effective_user
    bot = context.bot
    bot_user_account = bot.get_me()
    sticker_set_name = f"{user['username']}_by_{bot_user_account['username']}"
    query = update.callback_query

    try:
        with open(DEFAULT_STICKER_SET_PNG, 'rb') as png_sticker:
            success = bot.create_new_sticker_set(
                user['id'],
                sticker_set_name,
                sticker_set_name,  # Use the name also as the title for now
                png_sticker,
                DEFAULT_STICKER_SET_EMOJI)

        if success:
            query.edit_message_text(text=f"Created a new sticker set named: {sticker_set_name}")
        else:
            # Not sure if we ever end up here as the call seems to throw exceptions instead
            query.edit_message_text(text=f"Server reported failure during sticker set creation!")
    except BadRequest as exception:
        if exception.message == "Sticker set name is already occupied":
            query.edit_message_text(f"You have already created a sticker set: {sticker_set_name}")
        else:
            logger.exception("Failed unexpectedly when creating sticker set!")

    return ConversationHandler.END


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('stickers', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(create_set, pattern=f"^{State.CREATE_SET}$"),
            ],
    },
    fallbacks=[CommandHandler('stickers', start)]
)
