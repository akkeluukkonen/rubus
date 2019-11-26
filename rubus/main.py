#!/usr/bin/env python
"""
Main functionality of rubus for the time being.
Functionality will most likely be split in the future.
"""
import logging
import os
import time

import telegram
from telegram.error import NetworkError, Unauthorized


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
    bot = telegram.Bot(api_token)

    # get the first pending update_id, this is so we can skip over it in case
    # we get an "Unauthorized" exception.
    try:
        update_id = bot.get_updates()[0].update_id
    except IndexError:
        update_id = None


    logger.info("Init done. Starting...")
    while True:
        try:
            echo(bot)
        except NetworkError:
            time.sleep(1)
        except Unauthorized:
            # The user has removed or blocked the bot.
            update_id += 1


def echo(bot):
    """Echo the message the user sent."""
    global update_id
    # Request updates after the last update_id
    for update in bot.get_updates(offset=update_id, timeout=10):
        update_id = update.update_id + 1

        if update.message:  # your bot can receive updates without messages
            # Reply to the message
            update.message.reply_text(update.message.text)


if __name__ == '__main__':
    main()
