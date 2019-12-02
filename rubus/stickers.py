"""
Managing Telegram sticker sets and stickers using the bot interface.
"""
import enum
import logging
import os
import tempfile

from PIL import Image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters
from telegram.error import BadRequest

logger = logging.getLogger('rubus')

DEFAULT_STICKER_SET_PNG = "rubus/data/sticker_default.png"
DEFAULT_STICKER_SET_EMOJI = '\U0000267B'  # recycling symbol
STICKER_DIMENSION_SIZE_PIXELS = 512  # Per Telegram sticker requirements


class State(enum.Enum):
    """States for the ConversationHandler"""
    MENU = enum.auto()
    CREATE_SET = enum.auto()
    ADD_STICKER = enum.auto()
    ADD_STICKER_PHOTO = enum.auto()
    ADD_STICKER_EMOJI = enum.auto()


def start(update, context):  # pylint: disable=unused-argument
    """Present the user all available configuration options"""
    keyboard = [
        [InlineKeyboardButton("Create new sticker set", callback_data=str(State.CREATE_SET))],
        [InlineKeyboardButton("Add sticker to existing set", callback_data=str(State.ADD_STICKER))]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select configuration option:", reply_markup=reply_markup)
    return State.MENU


def _sticker_set_name(update, context):
    user = update.effective_user
    bot = context.bot
    bot_user_account = bot.get_me()
    sticker_set_name = f"{user['username']}_by_{bot_user_account['username']}"
    return sticker_set_name


def create_set(update, context):
    """Create a new sticker set, which is tied to the calling user

    The bot can manipulate this sticker set as it is the "co-creator" in this case.
    """
    user = update.effective_user
    bot = context.bot
    sticker_set_name = _sticker_set_name(update, context)
    query = update.callback_query

    try:
        with open(DEFAULT_STICKER_SET_PNG, 'rb') as png_sticker:
            success = bot.create_new_sticker_set(
                user['id'],
                sticker_set_name,
                sticker_set_name,  # Use the name also as the title for now
                png_sticker,
                DEFAULT_STICKER_SET_EMOJI)

        if success:
            query.edit_message_text(text=f"Created a new sticker set named: {sticker_set_name}")
        else:
            # Not sure if we ever end up here as the call seems to throw exceptions instead
            query.edit_message_text(text=f"Server reported failure during sticker set creation!")
    except BadRequest as exception:
        if exception.message == "Sticker set name is already occupied":
            query.edit_message_text(f"You have already created a sticker set: {sticker_set_name}")
        else:
            logger.exception("Failed unexpectedly when creating sticker set!")

    return ConversationHandler.END


def add_sticker(update, context):  # pylint: disable=unused-argument
    """Start routine of adding a sticker to an existing set

    The sticker will require a photo as well as a corresponding emoji,
    which will be gathered in the next steps.

    Note that currently the set is automatically the set created by the user through the bot.
    """
    query = update.callback_query
    query.message.edit_text(
        text="Send me the photo for the sticker and "
        "I'll try to automatically convert it according to the rules.")
    return State.ADD_STICKER_PHOTO


def add_sticker_photo(update, context):
    """Get a photo from the user and use store it to be added as a sticker"""
    # A photo can have multiple PhotoSize elements tied together
    # but we want to use the largest one for possible resize operations
    photos = update.message.photo
    photo = max(photos, key=lambda x: x.file_size)

    # Cache the file locally as we can't directly send the file id of a photo
    # as a sticker to the server. Telegram doesn't allow the file type to change
    # between objects, thus we have to reupload it manually.
    bot = context.bot
    file = bot.get_file(photo.file_id)
    temporary_directory = tempfile.TemporaryDirectory()
    filepath_jpg = os.path.join(temporary_directory.name, "photo.jpg")
    file.download(custom_path=filepath_jpg)

    # The file is stored as .jpg on Telegram servers
    # so we need to resize and convert it manually
    image_jpg = Image.open(filepath_jpg)
    # It is enough for one dimension to be STICKER_DIMENSION_SIZE_PIXELS
    longest_dimension = max(image_jpg.size)
    ratio = STICKER_DIMENSION_SIZE_PIXELS / longest_dimension
    width_new = int(image_jpg.size[0] * ratio)
    height_new = int(image_jpg.size[1] * ratio)
    image_resized = image_jpg.resize((width_new, height_new))
    filepath_png = os.path.join(temporary_directory.name, "photo.png")
    image_resized.save(filepath_png)

    context.user_data['photo_temporary_directory'] = temporary_directory
    context.user_data['photo_filepath'] = filepath_png

    update.message.reply_text(text="Send me the emojis (1 to 3) matching the photo.")
    return State.ADD_STICKER_EMOJI


def add_sticker_emoji(update, context):
    """Get emoji(s) from the user and push a create a new sticker to the current set"""
    user = update.effective_user
    bot = context.bot
    sticker_set_name = _sticker_set_name(update, context)
    filepath_png = context.user_data['photo_filepath']
    # TODO: Confirm message is emoji
    message = update.message
    emojis = message.text

    try:
        with open(filepath_png, 'rb') as png_sticker:
            success = bot.add_sticker_to_set(
                user['id'],
                sticker_set_name,
                png_sticker,
                emojis)

        if success:
            message.reply_text(text=f"Added a sticker to set {sticker_set_name}!")
        else:
            # Not sure if we ever end up here as the call seems to throw exceptions instead
            message.reply_text(text=f"Server reported failure when attempting to add sticker!")
    except BadRequest:
        logger.exception("Failed unexpectedly when adding a sticker!")
    finally:
        # Cleanup and remove all related files
        temporary_directory = context.user_data['photo_temporary_directory']
        temporary_directory.cleanup()
        del context.user_data['photo_temporary_directory']
        del context.user_data['photo_filepath']

    return ConversationHandler.END


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('stickers', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(create_set, pattern=f"^{State.CREATE_SET}$"),
            CallbackQueryHandler(add_sticker, pattern=f"^{State.ADD_STICKER}$"),
            ],
        State.ADD_STICKER_PHOTO: [
            MessageHandler(Filters.photo, add_sticker_photo),
            ],
        State.ADD_STICKER_EMOJI: [
            MessageHandler(Filters.text, add_sticker_emoji),
            ],
    },
    fallbacks=[CommandHandler('stickers', start)]
)
