"""
General helper functions which can be shared between multiple submodules.
"""

from telegram.ext import ConversationHandler


def confused(update, context):  # pylint: disable=unused-argument
    """Did not understand what the user was requesting"""
    message = update.message
    message.reply_text(
        "Sorry, I'm confused and didn't understand what you wanted me to do.\n"
        "Cancelling current operation.")
    return ConversationHandler.END
