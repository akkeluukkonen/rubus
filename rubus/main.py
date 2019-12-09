#!/usr/bin/env python
"""
Main functionality of rubus for the time being.
"""
import logging
import os

import telegram.ext

import stickers


formatter_stream = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler_stream = logging.StreamHandler()
handler_stream.setFormatter(formatter_stream)
logger = logging.getLogger('rubus')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler_stream)


def _get_api_token():
    try:
        with open("/run/secrets/API_TOKEN") as infile:
            api_token = infile.read().rstrip()
    except FileNotFoundError:
        api_token = os.environ['API_TOKEN']
    return api_token


def error(update, context):
    """Log unexpected errors for debugging"""
    logger.warning(f"Update {update} caused error {context.error!r}: {context.error}")


def main():
    """Run the bot."""
    logger.info("Initializing rubus...")

    api_token = _get_api_token()

    persistence = telegram.ext.PicklePersistence("rubus_data.pkl")
    updater = telegram.ext.Updater(api_token, use_context=True, persistence=persistence)
    updater.dispatcher.add_error_handler(error)
    updater.dispatcher.add_handler(stickers.handler_conversation)

    logger.info("Init done. Starting...")
    updater.start_polling(poll_interval=0.1)
    logger.info("Rubus active!")
    updater.idle()
    logger.info("Rubus halted. Exiting...")


if __name__ == '__main__':
    main()
