"""
Automatically post the latest Fok-It comic strip to a Telegram channel requesting it.
"""
import datetime
import enum
import logging
import os
import pickle
import random
import sqlite3
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
NOON = datetime.time(12, 00)
MONDAY_TO_FRIDAY = tuple(range(5))

FILEPATH_INDEX = os.path.join(CONFIG['filepaths']['storage'], "comics.db")
conn = sqlite3.connect(FILEPATH_INDEX)


class State(enum.IntEnum):
    """States for the ConversationHandler

    In a State the handler is waiting for the next message to arrive.
    The performed actions may depend on the message content.
    """
    MENU = enum.auto()
    SCHEDULE_MENU = enum.auto()
    SCHEDULE = enum.auto()


class Command(enum.IntEnum):
    """Commands for the ConversationHandler

    Can be directly used as a value for the CallbackQueryHandler from the InlineKeyboard.
    """
    POST_RANDOM = enum.auto()
    SCHEDULE_MENU = enum.auto()
    SCHEDULE = enum.auto()
    CANCEL = enum.auto()


def fetch_comic_url_latest(comic_url_homepage):
    """Fetch URL of the latest comic from its individual page"""
    response = requests.get(comic_url_homepage)
    soup = BeautifulSoup(response.content, 'html.parser')
    latest_comic = soup.find('figure')
    # Grab the link for the individual page of the comic as we can start crawling from that
    comic_uri_part = latest_comic.find('meta', {'itemprop': 'contentUrl'})['content']
    comic_url = f"{URL_BASE}{comic_uri_part}"
    return comic_url


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


def _download_comic_image(image_url):
    response = requests.get(image_url)
    image_data = response.content
    # Save the image locally with the same filename as the host server is using.
    image_filename = os.path.basename(image_url.split('/')[-1])
    image_filepath = os.path.join(CONFIG['filepaths']['storage'], image_filename)
    with open(image_filepath, 'wb') as image_file:
        image_file.write(image_data)
    return image_filepath


def download_comic(url):
    """Download the comic from a given URL

    Returns a dictionary with the relevant data.
    """
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    date_text_with_weekday = soup.find('span', {'class': 'date'}).text
    date_text = date_text_with_weekday.split(' ')[-1]
    try:
        date = datetime.datetime.strptime(date_text, r"%d.%m.%Y").date()
    except ValueError:
        # Comics released in the current year don't include the year explicitly in the text
        date = datetime.datetime.strptime(date_text, r"%d.%m.").date()
        today = datetime.datetime.now().date()
        date = date.replace(year=today.year)

    image_element = soup.find('img')
    # The element includes a low-res and high-res partial URI but we want only the high-res one,
    # which is in the attribute 'data-srcset' in the format "<link> 1920w"
    image_uri = image_element['data-srcset'].rstrip(" 1920w")
    # image_uri is of format '//hs.mediadelivery.fi/...'
    image_url = f"https:{image_uri}"
    image_filepath = _download_comic_image(image_url)

    data = {
        'date': date,
        'filepath': image_filepath,
    }
    return data


def fetch_comics_available():
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


def _update_index_of_comic(comic):
    cursor = conn.cursor()

    comic_latest_stored_date_str = cursor.execute(
        "SELECT date FROM images WHERE name = ? ORDER BY date DESC", (comic['name'],)).fetchone()
    if comic_latest_stored_date_str is not None:
        # SQLite annoyingly returns even single values in a tuple...
        comic_latest_stored_date_str = comic_latest_stored_date_str[0]

    comic_homepage_url = cursor.execute(
        "SELECT url FROM sources WHERE name = ?", (comic['name'],)).fetchone()[0]

    url_start_from = fetch_comic_url_latest(comic_homepage_url)
    for url in _fetch_comic_url_all(url_start_from):
        data = download_comic(url)

        date_str = data['date'].strftime(r"%Y-%m-%d")
        if date_str == comic_latest_stored_date_str:
            logger.debug(f"{comic['name']} for date {date_str} already indexed")
            break

        logger.debug(f"Fetched information for {comic['name']} of {date_str}")
        cursor.execute(
            "INSERT INTO images (name, date, filepath) values (?, ?, ?)",
            (comic['name'], date_str, data['filepath']))

    conn.commit()


def _create_database_tables(comics_available):
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE IF NOT EXISTS sources (name TEXT UNIQUE, url TEXT)")
    for comic in comics_available:
        cursor.execute("INSERT OR REPLACE INTO sources (name, url) values (?, ?)", (comic['name'], comic['url']))

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS images "
        "(name TEXT, date DATE, filepath TEXT NOT NULL, file_id TEXT, UNIQUE(name, date))")

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS daily_posts "
        "(chat_id INTEGER, name TEXT, UNIQUE(chat_id, name))")

    conn.commit()


def update_index():
    """Download all comics we haven't yet seen

    The data shall be stored in a SQLite database so that it can be easily accessed.
    """
    comics_available = fetch_comics_available()
    _create_database_tables(comics_available)

    for comic in comics_available:
        _update_index_of_comic(comic)

    # TODO: Upload directly to tg?

    logger.info("Database updated")


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


def _is_comic_scheduled(chat_id, name):
    cursor = conn.cursor()
    row = cursor.execute("SELECT 1 FROM daily_posts WHERE chat_id = ? AND name = ?", (chat_id, name)).fetchone()
    return row is not None


def schedule_menu(update, context):  # pylint: disable=unused-argument
    """Present the user the scheduling options"""
    chat_id = update.message.chat_id
    cursor = conn.cursor()
    comics = cursor.execute("SELECT name FROM sources").fetchall()

    buttons = []
    for name in comics:
        # TODO: What callback?
        if _is_comic_scheduled(chat_id, name):
            buttons.append(
                [InlineKeyboardButton(f"Stop posting {name} daily at noon", callback_data=name)])
        else:
            buttons.append(
                [InlineKeyboardButton(f"Start posting {name} daily at noon", callback_data=name)])

    keyboard = [
        *buttons,
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select option:", reply_markup=reply_markup)
    return State.SCHEDULE


def schedule(update, context):  # pylint: disable=unused-argument
    """Change the schedule of a comic"""
    chat_id = update.message.chat_id
    query = update.callback_query
    name = query.data

    if _is_comic_scheduled(chat_id, name):
        scheduling_disable(chat_id, name)
        query.message.edit_text(f"Scheduled {name} posting disabled")
    else:
        scheduling_enable(chat_id, name)
        query.message.edit_text(f"Scheduled {name} posting enabled at noon")

    return ConversationHandler.END

def scheduling_enable(chat_id, name):
    """Enable scheduled posting of a comic for a chat"""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO daily_posts values (?, ?)", (chat_id, name))
    conn.commit()


def scheduling_disable(chat_id, name):
    """Disable scheduled posting of a comic for a chat"""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_posts WHERE chat_id = ? AND name = ?", (chat_id, name))
    conn.commit()


def start(update, context):  # pylint: disable=unused-argument
    """Present the user all available options"""
    keyboard = [
        [InlineKeyboardButton("Post a random comic", callback_data=Command.POST_RANDOM)],
        [InlineKeyboardButton("Change the schedule of a daily comic", callback_data=Command.SCHEDULE)],
        [InlineKeyboardButton("Cancel", callback_data=Command.CANCEL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select option:", reply_markup=reply_markup)
    return State.MENU


def init(dispatcher):
    """At bot startup this function should be executed to initialize the jobs correctly"""
    logger.info("Updating database for comics")
    update_index()
    logger.info("Scheduling job to post comics daily")
    job_queue = dispatcher.job_queue
    job_queue.run_daily(post_comic_of_the_day, NOON, MONDAY_TO_FRIDAY)


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('fokit', start)], # TODO: Remove specifics
    states={
        State.MENU: [
            CallbackQueryHandler(post_random, pattern=f"^{Command.POST_RANDOM}$"),
            CallbackQueryHandler(schedule_menu, pattern=f"^{Command.SCHEDULE_MENU}$"),
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            ],
        State.SCHEDULE_MENU: [
            CallbackQueryHandler(schedule, pattern=f"^{Command.SCHEDULE}$"),
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            ],
        State.SCHEDULE: [
            CallbackQueryHandler(helper.cancel, pattern=f"^{Command.CANCEL}$"),
            CallbackQueryHandler(schedule),
            ],
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
