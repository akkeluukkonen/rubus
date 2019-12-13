#!/usr/bin/env python
"""
Main functionality of rubus for the time being.
"""
import logging
import os

import telegram.ext
from telegram.ext import ConversationHandler
from telegram.ext import CommandHandler, MessageHandler, Filters

from rubus import helper
from rubus import stickers


DOCKER_VOLUME_FILEPATH = "/data"
FILEPATH_LOG = os.path.join(DOCKER_VOLUME_FILEPATH, "rubus.log")
FILEPATH_DATA = os.path.join(DOCKER_VOLUME_FILEPATH, "bot-data.pkl")

formatter_stream = logging.Formatter(
    "%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s",
    datefmt="%H:%M:%S")
handler_stream = logging.StreamHandler()
handler_stream.setFormatter(formatter_stream)

formatter_file = logging.Formatter(
    "%(asctime)s.%(msecs)03d - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s")
handler_file = logging.FileHandler(FILEPATH_LOG, 'w')
handler_file.setFormatter(formatter_file)

logger = logging.getLogger('rubus')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler_stream)
logger.addHandler(handler_file)


def start(update, context):  # pylint: disable=unused-argument
    """Greet the user, basically a nop state"""
    message = update.message

    if update.effective_chat.type == 'private':
        message.reply_text(
            "Hello, thanks for messaging me.\n"
            "Now you can use all of my features even on other channels!",
            quote=False)
    else:
        message.reply_text("You should message the /start command to me in a private chat.")

    return ConversationHandler.END


def _get_api_token():
    with open("/run/secrets/API_TOKEN") as infile:
        api_token = infile.read().rstrip()
    return api_token


def error(update, context):
    """Log unexpected errors for debugging"""
    logger.warning(f"Update {update} caused error {context.error!r}: {context.error}")


def main():
    """Run the bot."""
    logger.info("Initializing rubus...")
    api_token = _get_api_token()
    persistence = telegram.ext.PicklePersistence(FILEPATH_DATA)
    updater = telegram.ext.Updater(api_token, use_context=True, persistence=persistence)
    updater.dispatcher.add_error_handler(error)

    handler_conversation = telegram.ext.ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            stickers.handler_conversation,
            ],
        states={
            # No higher level states yet implemented
        },
        fallbacks=[
            MessageHandler(Filters.all, helper.confused)
        ]
    )

    updater.dispatcher.add_handler(handler_conversation)

    logger.info("Init done. Starting...")
    updater.start_polling(poll_interval=0.1)
    logger.info("Rubus active!")
    updater.idle()
    logger.info("Rubus halted. Exiting...")


if __name__ == '__main__':
    main()
