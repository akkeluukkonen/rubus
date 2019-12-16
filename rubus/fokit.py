"""
Automatically post the latest Fok-It comic strip to a Telegram channel requesting it.
"""
import datetime
import enum
import http
import logging
import os
import pickle
import tempfile
import time

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters

from rubus import helper


logger = logging.getLogger('rubus')

URL_BASE = "https://hs.fi"
URL_FOKIT = f"{URL_BASE}/nyt/fokit"


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
    POST_RANDOM = enum.auto()
    SCHEDULING_DISABLE = enum.auto()
    SCHEDULING_ENABLE = enum.auto()
    CANCEL = enum.auto()


def fetch_comic_url_latest():
    """Fetch URL of the latest comic on its individual page"""
    response = requests.get(URL_FOKIT)
    soup = BeautifulSoup(response.content, 'html.parser')
    figure_elements = soup.find_all('figure')
    # Latest comic should be first available figure element
    figure_element_first = figure_elements[0]
    # Grab the link for the individual page of the comic as we can start crawling from that
    comic_uri_part = figure_element_first.find('meta', {'itemprop': 'contentUrl'})['content']
    comic_url = f"{URL_BASE}{comic_uri_part}"
    return comic_url


def _fetch_comic_url_all(url_current):
    # Fake the first one to be of the same form
    uri_previous_part = {'href': url_current.lstrip(URL_BASE)}
    while uri_previous_part is not None:
        url_current = f"{URL_BASE}/{uri_previous_part['href']}"
        yield url_current

        # Avoid looking like an attacker
        time.sleep(0.2)

        response = requests.get(url_current)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Crawl backwards using the "Previous" button on the page
        uri_previous_part = soup.find('a', {'class': 'article-navlink prev'})


def fetch_comic_url_all():
    """Fetch all of the URLs for the Fok-It comics"""
    latest_url = fetch_comic_url_latest()
    comic_urls = list(_fetch_comic_url_all(latest_url))
    return comic_urls


def fetch_comic_images_all(download_directory):
    """Fetch all of the images for the Fok-It comics

    Data will be saved in a pickled file to the given download directory as a pickled index file,
    and as separate image files.

    Index file format:
    [
        {'date': "Monday, 1.1.2018", 'filepath': "download_filepath/<image_identifier>.jpg},
        {'date': "Tuesay, 2.1.2018", 'filepath': "download_filepath/<image_identifier>.jpg},
        ...
    ]
    """
    index = []
    for url in fetch_comic_url_all():
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        date = soup.find('span', {'class': 'date'}).text
        image_element = soup.find_all('img')
        # The element includes a low-res and high-res partial URI but we want only the high-res one,
        # which is in the attribute 'data-srcset' in the format "<link> 1920w"
        image_uri = image_element['data-srcset'].rstrip(" 1920w")
        image_url = f"{URL_BASE}/{image_uri}"
        response = requests.get(image_url)
        image_data = response.content

        image_filename = os.path.basename(image_url.split('/')[-1])
        image_filepath = os.path.join(download_directory, image_filename)
        with open(image_filepath, "wb") as image_file:
            image_file.write(image_data)

        index.append({'date': date, 'filepath': image_filepath})

    index_filepath = os.path.join(download_directory, "index-fokit.pkl")
    with open(index_filepath, "wb") as index_file:
        pickle.dump(index, index_file)


def _fetch_comic_latest_image_url():
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


def _post_comic_from_url(context, url, message=None):
    chat_id = context.job.context
    response = requests.get(url)
    image_data = response.content

    # We need a filelike object for bot.send_photo(...)
    with tempfile.TemporaryFile() as image_file:
        image_file.write(image_data)
        image_file.seek(0)  # Rewind back to start for the bot to read it correctly

        if message:
            context.bot.send_photo(chat_id, image_file, message)
        else:
            context.bot.send_photo(chat_id, image_file)


def _post_comic_latest(context):
    chat_id = context.job.context
    latest_url = _fetch_comic_latest_url()

    if latest_url is None:
        context.bot.send_message(chat_id, "Failed to fetch the latest Fok-It!")
        return

    _post_comic_from_url(context, latest_url, "Fok-It of the day")


def post_random(update, context):
    """Post a random Fok-It on demand"""
    # Need to build a database of the available images
    # From the frontpage grab the link for the page of the first individual image
    # Crawl backwards from there to gather all of the links since they don't seem to be deterministic
    # From the links grab the URLs for the actual images
    # Store everything in a separate persistent storage to avoid re-crawling on subsequent starts
    # When demanded, grab a random image URL and post the image on the channel
    raise NotImplementedError
    return ConversationHandler.END


def scheduling_enable(update, context):
    """Enable scheduled posting of the comic strips"""
    context.chat_data['fokit-scheduled'] = True
    query = update.callback_query
    query.message.edit_text("Scheduled Fok-It posting enabled at noon on weekdays")
    return ConversationHandler.END


def scheduling_disable(update, context):
    """Disable scheduled posting of the comic strips"""
    context.chat_data['fokit-scheduled'] = False
    query = update.callback_query
    query.message.edit_text("Scheduled Fok-It posting disabled")
    return ConversationHandler.END


def cancel(update, context):  # pylint: disable=unused-argument
    """Don't make any changes"""
    query = update.callback_query
    query.message.edit_text("Canceled")
    return ConversationHandler.END


def start(update, context):
    """Present the user all available fokit configuration options"""
    if 'fokit-scheduled' not in context.chat_data:
        context.chat_data['fokit-scheduled'] = False

    post = InlineKeyboardButton("Post a random Fok-It", callback_data=Command.POST_RANDOM)

    if context.chat_data['fokit-scheduled']:
        scheduled = InlineKeyboardButton("Stop posting Fok-It daily at noon", callback_data=Command.SCHEDULING_DISABLE)
    else:
        scheduled = InlineKeyboardButton("Start posting Fok-It daily at noon", callback_data=Command.SCHEDULING_ENABLE)

    keyboard = [
        [scheduled],
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
        [post],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select option:", reply_markup=reply_markup)
    return State.MENU


def init(dispatcher):
    """At bot startup this function should be executed to initialize the jobs correctly"""
    noon = datetime.time(12, 00)
    monday_to_friday = tuple(range(5))

    job_queue = dispatcher.job_queue
    chat_data = dispatcher.chat_data
    for chat_id in chat_data:
        # Create the job even for chats not using the feature as it is easier to simply
        # enable / disable the job per chat instead of creating and destroying it repeatedly
        job = job_queue.run_daily(_post_comic_latest, noon, monday_to_friday, context=chat_id)
        job.enabled = chat_data.get('fokit-scheduled', False)


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('fokit', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(post_random, pattern=f"^{Command.POST_RANDOM}$"),
            CallbackQueryHandler(scheduling_disable, pattern=f"^{Command.SCHEDULING_DISABLE}$"),
            CallbackQueryHandler(scheduling_enable, pattern=f"^{Command.SCHEDULING_ENABLE}$"),
            CallbackQueryHandler(cancel, pattern=f"^{Command.CANCEL}$"),
            ],
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
