"""
General helper functions which can be shared between multiple submodules.
"""
import importlib.resources
import json

from telegram.ext import ConversationHandler


def config_load():
    """Load stored configuration from disk

    Configuration should be stored as JSON along with the module files.

    :return: Dictionary of the configuration
    """
    config_text = importlib.resources.read_text("rubus", "config.json")
    data = json.loads(config_text)
    return data


def confused(update, context):  # pylint: disable=unused-argument
    """Did not understand what the user was requesting"""
    message = update.message
    message.reply_text(
        "Sorry, I'm confused and didn't understand what you wanted me to do.\n"
        "Cancelling current operation.")
    return ConversationHandler.END
