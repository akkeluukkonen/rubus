"""
Reminders of upcoming events requested by users.
"""
import enum
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters

from rubus import helper


logger = logging.getLogger('rubus')

CONFIG = helper.config_load()


class State(enum.IntEnum):
    """States for the ConversationHandler

    In a State the handler is waiting for the next message to arrive.
    The performed actions may depend on the message content.
    """
    MENU = enum.auto()


class Command(enum.IntEnum):
    """Commands for the ConversationHandler

    Can be directly used as a value for the CallbackQueryHandler from the InlineKeyboard.
    """
    CANCEL = enum.auto()


def start(update, context):
    """Present the user all available reminder configuration options"""
    keyboard = [
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select option:", reply_markup=reply_markup)
    return State.MENU


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('reminders', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            ],
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
