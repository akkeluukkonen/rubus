"""
Automatically post the latest Fok-It comic strip to a Telegram channel requesting it.
"""
import datetime
import enum
import http
import logging
import tempfile

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters

from rubus import helper


logger = logging.getLogger('rubus')

URL_FOKIT = "https://hs.fi/nyt/fokit"


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
    POSTING_START = enum.auto()
    POSTING_STOP = enum.auto()


def _fetch_latest_comic_url():
    response = requests.get(URL_FOKIT)
    if response.status_code != http.HTTPStatus.OK:
        logger.warning(f"Failed to fetch comic due to HTTP code {response.status_code}!")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    img_element = soup.find_all('img')
    # Latest comic should be first available img element
    img_element_first = img_element[0]
    # The element includes a low-res and high-res link but we want only the high-res one,
    # which is the first one in attribute 'data-srcset' containing whitespace separated links
    image_urls = img_element_first.attrs['data-srcset'].split()
    latest_uri = image_urls[0]
    latest_url = f"https:{latest_uri}"
    return latest_url


def _post_latest_comic(context):
    chat_id = context.job.context
    latest_url = _fetch_latest_comic_url()

    if latest_url is None:
        context.bot.send_message(chat_id, "Failed to fetch the latest Fok-It!")
        return

    response = requests.get(latest_url)
    image_data = response.content

    # We need a filelike object for bot.send_photo(...)
    with tempfile.TemporaryFile() as image_file:
        image_file.write(image_data)
        image_file.seek(0)  # Rewind back to start for the bot to read it correctly
        context.bot.send_photo(chat_id, image_file, "Fok-It of the day")


def posting_start(update, context):
    """Start posting the comic strips daily at noon from Monday to Friday"""
    noon = datetime.time(12, 00)
    monday_to_friday = list(range(5))
    query = update.callback_query
    job = context.job_queue.run_daily(
        _post_latest_comic, noon, monday_to_friday, context=query.message.chat_id)
    context.chat_data['job'] = job

    query.message.edit_text("Scheduled Fok-It posting enabled")
    return ConversationHandler.END


def posting_stop(update, context):
    """Stop automatic posting"""
    del context.chat_data['job']
    query = update.callback_query
    query.message.edit_text("Scheduled Fok-It posting disabled")
    return ConversationHandler.END


def start(update, context):
    """Present the user all available fokit configuration options"""
    if 'fokit-enabled' not in context.chat_data:
        context.chat_data['fokit-enabled'] = False

    if context.chat_data['fokit-enabled']:
        button = InlineKeyboardButton("Stop posting Fok-It daily at noon", callback_data=Command.POSTING_STOP)
    else:
        button = InlineKeyboardButton("Start posting Fok-It daily at noon", callback_data=Command.POSTING_START)

    keyboard = [[button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select configuration option:", reply_markup=reply_markup)
    return State.MENU


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('fokit', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(posting_start, pattern=f"^{Command.POSTING_START}$"),
            CallbackQueryHandler(posting_stop, pattern=f"^{Command.POSTING_STOP}$"),
            ],
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
