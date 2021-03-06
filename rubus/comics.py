"""
Handle posting of hs.fi comics when requested.

The bot can automatically download local copies of the comics available at hs.fi,
then post then either on request or as daily scheduled posts.
"""
import datetime
import enum
import functools
import itertools
import logging
import os
import queue
import threading
import urllib.parse

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters

from rubus import helper


logger = logging.getLogger('rubus')

CONFIG = helper.config_load()
URL_SCHEME = "https"
URL_HOST = "hs.fi"
URL_BASE = f"{URL_SCHEME}://{URL_HOST}"
URL_COMICS = f"{URL_BASE}/sarjakuvat/"

# Multi-threading SQL queries shall be synchronized over these Queue objects
DATABASE_FILEPATH = os.path.join(CONFIG['filepaths']['storage'], "comics.db")
queries = queue.Queue()
results = queue.Queue()
database_query = functools.partial(helper.database_query, queries, results)
database_query_single = functools.partial(helper.database_query_single, queries, results)


class State(enum.IntEnum):
    """States for the ConversationHandler

    In a State the handler is waiting for the next message to arrive.
    The performed actions may depend on the message content.
    """
    MENU = enum.auto()
    SCHEDULE = enum.auto()
    RANDOM = enum.auto()


class Command(enum.IntEnum):
    """Commands for the ConversationHandler

    Can be directly used as a value for the CallbackQueryHandler from the InlineKeyboard.
    """
    SCHEDULE_MENU = enum.auto()
    RANDOM_MENU = enum.auto()
    CANCEL = enum.auto()


def init(dispatcher):
    """At bot startup this function should be executed to initialize the jobs correctly"""
    logger.info("Setting up database worker")
    worker = threading.Thread(
        target=helper.database_worker,
        args=(DATABASE_FILEPATH, queries, results),
        daemon=True)
    worker.start()

    logger.info("Updating database for comics")
    _create_database_tables()
    _update_index()

    logger.info("Scheduling job to post comics daily")
    job_queue = dispatcher.job_queue
    # Grab the timezone of the environment and pass it on
    # since from python-telegram-bot >= 12.3.0 the timezone handling defaults to UTC
    tzinfo = datetime.datetime.now().astimezone().tzinfo
    time_update = datetime.time(hour=11, minute=45, tzinfo=tzinfo)
    time_post = datetime.time(hour=12, minute=00, tzinfo=tzinfo)
    job_queue.run_daily(_update_index, time_update)
    job_queue.run_daily(_post_comic_of_the_day, time_post)


def _create_database_tables():
    database_query("CREATE TABLE IF NOT EXISTS sources (name TEXT UNIQUE, url TEXT)")
    database_query(
        "CREATE TABLE IF NOT EXISTS images "
        "(name TEXT, date DATE, filepath TEXT NOT NULL, file_id TEXT)")
    database_query(
        "CREATE TABLE IF NOT EXISTS daily_posts "
        "(chat_id INTEGER, name TEXT, UNIQUE(chat_id, name))")


def _update_index(*args):  # pylint: disable=unused-argument
    """Download all comics we haven't yet stored"""
    comics_available = _fetch_comics_available()
    for comic in comics_available:
        database_query(
            "INSERT OR REPLACE INTO sources (name, url) values (?, ?)", comic['name'], comic['url'])
        _update_index_of_comic(comic)
    logger.info("Database updated")


def _update_index_of_comic(comic):
    comic_latest_stored_date_str = database_query_single(
        "SELECT date FROM images WHERE name = ? ORDER BY date DESC", comic['name'])
    comic_homepage_url = database_query_single(
        "SELECT url FROM sources WHERE name = ?", comic['name'])

    url_start_from = _fetch_comic_url_latest(comic_homepage_url)
    for url in _fetch_comic_url_all(url_start_from):
        data = _download_comic(url)

        date_str = data['date'].strftime(r"%Y-%m-%d")
        if date_str == comic_latest_stored_date_str:
            logger.debug(f"{comic['name']} for date {date_str} already indexed")
            break

        logger.debug(f"Fetched information for {comic['name']} of {date_str}")
        database_query(
            "INSERT INTO images (name, date, filepath) values (?, ?, ?)",
            comic['name'], date_str, data['filepath'])


def _start(update, context):  # pylint: disable=unused-argument
    """Present the user all available options"""
    keyboard = [
        [InlineKeyboardButton("Post a random comic", callback_data=Command.RANDOM_MENU)],
        [InlineKeyboardButton("Change the schedule of a daily comic", callback_data=Command.SCHEDULE_MENU)],
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select option:", reply_markup=reply_markup)
    return State.MENU


def _random_menu(update, context):  # pylint: disable=unused-argument
    """Present the user the comic options"""
    comics = database_query("SELECT name FROM sources")
    buttons = [InlineKeyboardButton(f"{name}", callback_data=name) \
        for name in itertools.chain.from_iterable(comics)]
    buttons_grouped = helper.group_elements(buttons, 2)
    keyboard = [
        *buttons_grouped,
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    query.message.edit_text("Select option:", reply_markup=reply_markup)
    return State.RANDOM


def _random_post(update, context):
    """Post a random comic"""
    query = update.callback_query
    name = query.data

    date, filepath, file_id = database_query_single(
        "SELECT date, filepath, file_id FROM images WHERE name = ? ORDER BY RANDOM() LIMIT 1", name)

    query.message.edit_text(f"{name} of {date}")
    chat_id = query.message.chat['id']

    if file_id is not None:
        context.bot.send_photo(chat_id, file_id)
    else:
        with open(filepath, 'rb') as image:
            context.bot.send_photo(chat_id, image)

    return ConversationHandler.END


def _schedule_menu(update, context):  # pylint: disable=unused-argument
    """Present the user the scheduling options"""
    chat_id = update.callback_query.message.chat_id
    comics = database_query("SELECT name FROM sources")

    buttons = []
    for name in itertools.chain.from_iterable(comics):
        if _is_comic_scheduled(chat_id, name):
            text = f"Stop posting {name} daily at noon"
        else:
            text = f"Start posting {name} daily at noon"
        buttons.append([InlineKeyboardButton(text, callback_data=name)])

    keyboard = [
        *buttons,
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    query.message.edit_text("Select option:", reply_markup=reply_markup)
    return State.SCHEDULE


def _schedule_post(update, context):  # pylint: disable=unused-argument
    """Change the schedule of a comic"""
    query = update.callback_query
    chat_id = query.message.chat_id
    name = query.data

    if _is_comic_scheduled(chat_id, name):
        database_query("DELETE FROM daily_posts WHERE chat_id = ? AND name = ?", chat_id, name)
        query.message.edit_text(f"Scheduled {name} posting disabled")
    else:
        database_query("INSERT INTO daily_posts values (?, ?)", chat_id, name)
        query.message.edit_text(f"Scheduled {name} posting enabled at noon")

    return ConversationHandler.END


def _is_comic_scheduled(chat_id, name):
    row = database_query_single("SELECT 1 FROM daily_posts WHERE chat_id = ? AND name = ?", chat_id, name)
    return row is not None


def _post_comic_of_the_day(context):
    """Post the latest available comic if one is available

    Automatically go through all registered chats and stored comics.
    """
    today_str = datetime.date.today().strftime(r"%Y-%m-%d")

    for chat_id, name in database_query("SELECT chat_id, name FROM daily_posts"):
        filepath = database_query_single(
            "SELECT filepath FROM images "
            "WHERE name = ? AND date = ? ORDER BY date DESC LIMIT 1", name, today_str)

        if filepath is None:
            continue

        with open(filepath, 'rb') as image:
            context.bot.send_photo(chat_id, image, f"{name} of the day", disable_notification=True)


def _download_comic(url):
    """Download the comic from a given URL

    Returns a dictionary with the relevant data.
    """
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    date_text_with_day_of_week = soup.find('span', {'class': 'date'}).text
    date_text = date_text_with_day_of_week.split(' ')[-1]
    try:
        date = datetime.datetime.strptime(date_text, r"%d.%m.%Y").date()
    except ValueError:
        # Comics released in the current year don't include the year by default in the text
        today = datetime.datetime.now().date()
        date_text = f"{date_text}{today.year}"
        date = datetime.datetime.strptime(date_text, r"%d.%m.%Y").date()

    image_element = soup.find('img')
    # The element includes a low-res and high-res partial URI but we want only the high-res one,
    # which is in the attribute 'data-srcset' in the format "<link> 1920w"
    image_uri = image_element['data-srcset'].rstrip(" 1920w")
    # image_uri is of format '//hs.mediadelivery.fi/...'
    image_url = f"https:{image_uri}"
    image_filepath = __download_comic_image(image_url)

    data = {
        'date': date,
        'filepath': image_filepath,
    }
    return data


def __download_comic_image(image_url):
    response = requests.get(image_url)
    image_data = response.content
    # Save the image locally with the same filename as the host server is using.
    image_filename = os.path.basename(image_url.split('/')[-1])
    image_filepath = os.path.join(CONFIG['filepaths']['storage'], image_filename)
    with open(image_filepath, 'wb') as image_file:
        image_file.write(image_data)
    return image_filepath


def _fetch_comics_available():
    """Fetch all available comics from the frontpage at URL_COMICS"""
    response = requests.get(URL_COMICS)
    soup = BeautifulSoup(response.content, 'html.parser')

    comic_data = []
    comic_contents = soup.find_all('div', {'class': 'cartoon-content'})
    for content in comic_contents:
        name = content.find('span', {'class': 'title'}).get_text()
        uri_part = content.find('meta', {'itemprop': 'contentUrl'})['content']
        url = f"{URL_BASE}{uri_part}"
        comic_data.append({'name': name, 'url': url})
    return comic_data


def _fetch_comic_url_all(url_current):
    # Fake the first one to be of the same form without the base part
    uri_previous_part = {'href': url_current[len(URL_BASE):]}
    while uri_previous_part is not None:
        url_current = urllib.parse.urlunsplit(
            (URL_SCHEME, URL_HOST, uri_previous_part['href'], "", "")
        )
        yield url_current

        response = requests.get(url_current)
        soup = BeautifulSoup(response.content, 'html.parser')
        # Crawl backwards using the "Previous" button on the page
        uri_previous_part = soup.find('a', {'class': 'article-navlink prev'})


def _fetch_comic_url_latest(comic_url_homepage):
    """Fetch URL of the latest comic from its individual page"""
    response = requests.get(comic_url_homepage)
    soup = BeautifulSoup(response.content, 'html.parser')
    latest_comic = soup.find('figure')
    # Grab the link for the individual page of the comic as we can start crawling from that
    comic_uri_part = latest_comic.find('meta', {'itemprop': 'contentUrl'})['content']
    comic_url = f"{URL_BASE}{comic_uri_part}"
    return comic_url


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('comics', _start)],
    states={
        State.MENU: [
            CallbackQueryHandler(_random_menu, pattern=f"^{Command.RANDOM_MENU}$"),
            CallbackQueryHandler(_schedule_menu, pattern=f"^{Command.SCHEDULE_MENU}$"),
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            ],
        State.SCHEDULE: [
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            CallbackQueryHandler(_schedule_post),
            ],
        State.RANDOM: [
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            CallbackQueryHandler(_random_post),
        ]
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
