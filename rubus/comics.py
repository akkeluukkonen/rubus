"""
Automatically post the latest Fok-It comic strip to a Telegram channel requesting it.
"""
import datetime
import enum
import logging
import os
import pickle
import random
import urllib.parse

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters

from rubus import helper


logger = logging.getLogger('rubus')

CONFIG = helper.config_load()
FILEPATH_INDEX = os.path.join(CONFIG['filepaths']['storage'], "fokit_index.pkl")  # TODO: Remove specific
URL_SCHEME = "https"
URL_HOST = "hs.fi"
URL_BASE = f"{URL_SCHEME}://{URL_HOST}"
URL_COMICS = f"{URL_BASE}/sarjakuvat/"
URL_FOKIT = f"{URL_BASE}/nyt/fokit"  # TODO: Remove specific
NOON = datetime.time(12, 00)
MONDAY_TO_FRIDAY = tuple(range(5))


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


def fetch_comic_url_latest(url_comic):
    """Fetch URL of the latest comic from its individual page"""
    response = requests.get(url_comic)
    soup = BeautifulSoup(response.content, 'html.parser')
    latest_comic = soup.find('figure')
    # Grab the link for the individual page of the comic as we can start crawling from that
    comic_uri_part = latest_comic.find('meta', {'itemprop': 'contentUrl'})['content']
    comic_url = f"{URL_BASE}{comic_uri_part}"
    return comic_url


def _fetch_comic_url_all(url_current):
    # Fake the first one to be of the same form
    uri_previous_part = {'href': url_current.lstrip(URL_BASE)}
    while uri_previous_part is not None:
        url_current = urllib.parse.urlunsplit(
            (URL_SCHEME, URL_HOST, uri_previous_part['href'], "", "")
        )
        yield url_current

        response = requests.get(url_current)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Crawl backwards using the "Previous" button on the page
        uri_previous_part = soup.find('a', {'class': 'article-navlink prev'})


def fetch_comic_information(url):
    """Fetch all relevant information related to a comic

    Simultaneously save the image file to our dedicated storage location using the same
    filename as the host server is using. This filepath is stored in the returned dict.

    :return: Dictionary of format
        {
            'date': "Maanantai, 2.1.2019",
            'filepath': "download_filepath/<image_identifier>.jpg},
            'url: "url"
        }
    """
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    date = soup.find('span', {'class': 'date'}).text
    # Comics released in current year don't include the year explicitly
    if date.endswith('.'):
        current_year = datetime.datetime.today().year
        date += str(current_year)

    image_element = soup.find('img')
    # The element includes a low-res and high-res partial URI but we want only the high-res one,
    # which is in the attribute 'data-srcset' in the format "<link> 1920w"
    image_uri = image_element['data-srcset'].rstrip(" 1920w")
    # image_uri is of format '//hs.mediadelivery.fi/...'
    image_url = f"https:{image_uri}"
    response = requests.get(image_url)
    image_data = response.content

    image_filename = os.path.basename(image_url.split('/')[-1])
    # TODO: Need to include name of specific comic into the storage path!
    image_filepath = os.path.join(CONFIG['filepaths']['storage'], image_filename)
    with open(image_filepath, 'wb') as image_file:
        image_file.write(image_data)

    data = {
        'date': date,
        'filepath': image_filepath,
        'url': url
    }
    return data


def fetch_comics_available():
    """Fetch all available comics from the frontpage at URL_COMICS"""
    response = requests.get(URL_COMICS)
    soup = BeautifulSoup(response.content, 'html.parser')

    comic_data = []
    comic_contents = soup.find_all('div', {'class': 'cartoon-content'})
    for content in comic_contents:
        title = content.find('span', {'class': 'title'}).get_text()
        uri_part = content.find('meta', {'itemprop': 'contentUrl'})['content']
        url = f"{URL_BASE}{uri_part}"
        comic_data.append({'title': title, 'url': url})

    return comic_data


def update_index():
    """Fetch all of the images for the Fok-It comics # TODO: Remove specifics

    Data will be saved in a pickled file to the given download directory as a pickled index file,
    and as separate image files.

    Index file format:
    [
        {oldest}
        ...
        {
            'date': "Maanantai, 2.1.2019",
            'filepath': "download_filepath/<image_identifier>.jpg},
            'url: "<url_to_comic_page>"
        },
        ...
        {<latest>},
    ]
    """
    # Grab the current index to avoid creating duplicate entries and crawling unnecessary far
    # if the same data was already crawled earlier
    index = []
    if os.path.exists(FILEPATH_INDEX):
        with open(FILEPATH_INDEX, 'rb') as index_file:
            index = pickle.load(index_file)

    latest_indexed = index[-1] if index else None
    # Crawl backwards from the latest available comic
    results = []
    url_start_from = fetch_comic_url_latest(URL_FOKIT)  # TODO: Remove specifics
    for url in _fetch_comic_url_all(url_start_from):
        data = fetch_comic_information(url)

        if data == latest_indexed:
            # TODO: Remove specifics
            logger.debug(f"Fok-It for date {data['date']} already indexed")
            break

        # TODO: Remove specifics
        logger.debug(f"Fetched information for Fok-It of {data['date']}")
        results.append(data)

    # Ensure order is correct so that the latest result is last
    index.extend(results[::-1])
    with open(FILEPATH_INDEX, 'wb') as index_file:
        pickle.dump(index, index_file)

    return index


def post_comic_of_the_day(context):
    """Post the latest available comic

    # TODO: Remove specifics
    Basically this will post the Fok-It of the day assuming you call it correctly on a weekday.
    """
    index = update_index()

    # TODO: Fix the date system more elegantly
    _, image_latest_date_str = index[-1]['date'].split()
    image_latest_date = datetime.datetime.strptime(image_latest_date_str, r"%d.%m.%Y").date()
    if image_latest_date != datetime.date.today():
        logger.debug("Latest comic was not of today!")
        return

    image_latest_filepath = index[-1]['filepath']
    with open(image_latest_filepath, 'rb') as image_file:
        chat_id = context.job.context
        context.bot.send_photo(chat_id, image_file, "Fok-It of the day")


def post_random(update, context):
    """Post a random Fok-It""" # TODO: Remove specifics
    with open(FILEPATH_INDEX, 'rb') as index_file:
        index = pickle.load(index_file)

    query = update.callback_query
    image_random = random.choice(index)
    with open(image_random['filepath'], 'rb') as image_file:
        chat_id = query.message.chat['id']
        context.bot.send_photo(chat_id, image_file)

    # TODO: Remove specifics
    query.message.edit_text(f"Fok-It of {image_random['date']}")

    return ConversationHandler.END


def scheduling_enable(update, context):
    """Enable scheduled posting of the comic strips"""
    # TODO: Remove specifics
    context.chat_data['fokit-scheduled'] = True
    query = update.callback_query
    chat_id = query.message.chat['id']

    context.job_queue.run_daily(post_comic_of_the_day, NOON, MONDAY_TO_FRIDAY, context=chat_id)

    # TODO: Remove specifics
    query.message.edit_text("Scheduled Fok-It posting enabled at noon on weekdays")
    return ConversationHandler.END


def scheduling_disable(update, context):
    """Disable scheduled posting of the comic strips"""
    # TODO: Remove specifics
    context.chat_data['fokit-scheduled'] = False
    query = update.callback_query
    chat_id = query.message.chat['id']

    job = next(job for job in context.job_queue.jobs() if job.context == chat_id)
    job.schedule_removal()

    # TODO: Remove specifics
    query.message.edit_text("Scheduled Fok-It posting disabled")
    return ConversationHandler.END


def start(update, context):
    """Present the user all available fokit configuration options"""
    # TODO: Rework to be more generalized
    if 'fokit-scheduled' not in context.chat_data:
        context.chat_data['fokit-scheduled'] = False

    post = InlineKeyboardButton("Post a random Fok-It", callback_data=Command.POST_RANDOM)

    if context.chat_data['fokit-scheduled']:
        scheduled = InlineKeyboardButton("Stop posting Fok-It daily at noon", callback_data=Command.SCHEDULING_DISABLE)
    else:
        scheduled = InlineKeyboardButton("Start posting Fok-It daily at noon", callback_data=Command.SCHEDULING_ENABLE)

    keyboard = [
        [scheduled],
        [post],
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select option:", reply_markup=reply_markup)
    return State.MENU


def init(dispatcher):
    """At bot startup this function should be executed to initialize the jobs correctly"""
    # TODO: Rework to be more generalized
    job_queue = dispatcher.job_queue
    chat_data = dispatcher.chat_data
    for chat_id in chat_data:
        # Create the job even for chats not using the feature as it is easier to simply
        # enable / disable the job per chat instead of creating and destroying it repeatedly
        job = job_queue.run_daily(post_comic_of_the_day, NOON, MONDAY_TO_FRIDAY, context=chat_id)
        job.enabled = chat_data[chat_id].get('fokit-scheduled', False)

    logger.info("Updating index for Fok-It comics")
    update_index()


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('fokit', start)], # TODO: Remove specifics
    states={
        State.MENU: [
            CallbackQueryHandler(post_random, pattern=f"^{Command.POST_RANDOM}$"),
            CallbackQueryHandler(scheduling_disable, pattern=f"^{Command.SCHEDULING_DISABLE}$"),
            CallbackQueryHandler(scheduling_enable, pattern=f"^{Command.SCHEDULING_ENABLE}$"),
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            ],
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
