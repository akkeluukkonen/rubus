#!/usr/bin/env python
"""
Main functionality of rubus for the time being.
Functionality will most likely be split in the future.
"""
import logging
import os

import telegram.ext


formatter_stream = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler_stream = logging.StreamHandler()
handler_stream.setFormatter(formatter_stream)
logger = logging.getLogger('rubus')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler_stream)

update_id = None


def _get_api_token():
    try:
        with open("/run/secrets/API_TOKEN") as infile:
            api_token = infile.read().rstrip()
    except FileNotFoundError:
        api_token = os.environ['API_TOKEN']
    return api_token


def main():
    """Run the bot."""
    logger.info("Initializing rubus...")

    api_token = _get_api_token()
    updater = telegram.ext.Updater(api_token, use_context=True)
    updater.dispatcher.add_handler(
        telegram.ext.MessageHandler(
            telegram.ext.Filters.text,
            echo
        ))

    logger.info("Init done. Starting...")
    updater.start_polling(poll_interval=0.1)

    logger.info("Rubus active!")
    updater.idle()
    logger.info("Rubus halted. Exiting...")


def echo(update, context):  # pylint: disable=unused-argument
    """Echo the message the user sent."""
    update.message.reply_text(update.message.text)

if __name__ == '__main__':
    main()
