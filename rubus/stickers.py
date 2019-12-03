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
    ADD_STICKER_START = enum.auto()
    ADD_STICKER_PHOTO = enum.auto()
    ADD_STICKER_EMOJI = enum.auto()
    CREATE_SET = enum.auto()


def start(update, context):  # pylint: disable=unused-argument
    """Present the user all available sticker configuration options"""
    keyboard = [
        [InlineKeyboardButton("Add sticker to channel set", callback_data=str(State.ADD_STICKER_START))],
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


def add_sticker_start(update, context):  # pylint: disable=unused-argument
    """Start routine of adding a sticker to an existing set

    The sticker will require a photo as well as a corresponding emoji,
    which will be gathered in the next steps.

    If the channel has no dedicated sticker set yet,
    one will be created during this process.
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
    # TODO: Confirm message is emoji
    bot = context.bot
    message = update.message
    sticker_set_name = _sticker_set_name(update, context)
    emojis = message.text
    context.user_data['emojis'] = emojis

    try:
        bot.get_sticker_set(sticker_set_name)
        _add_sticker_to_set(update, context)
        return ConversationHandler.END
    except BadRequest as exception:
        # "Stickerset_invalid" is sent when the set doesn't exist
        if exception.message != "Stickerset_invalid":
            logger.exception("Failed unexpectedly when creating sticker set!")
            raise

    message.reply_text("No sticker sets were available. Send me the name you want to use for the sticker set.")
    return State.CREATE_SET


def _add_sticker_to_set(update, context):
    user = update.effective_user
    bot = context.bot
    message = update.message
    sticker_set_name = _sticker_set_name(update, context)
    filepath_png = context.user_data['photo_filepath']
    emojis = context.user_data['emojis']

    try:
        with open(filepath_png, 'rb') as png_sticker:
            success = bot.add_sticker_to_set(
                user['id'],
                sticker_set_name,
                png_sticker,
                emojis)

        if success:
            sticker_set = bot.get_sticker_set(sticker_set_name)
            message.reply_text(text=f"Added a sticker to set {sticker_set.title}!", quote=False)
            temporary_directory = context.user_data['photo_temporary_directory']
            temporary_directory.cleanup()
            del context.user_data['photo_temporary_directory']
            del context.user_data['photo_filepath']
            del context.user_data['emojis']
        else:
            # Not sure if we ever end up here as the call seems to throw exceptions instead
            message.reply_text(text=f"Server reported failure when attempting to add sticker!", quote=False)
    except BadRequest:
        logger.exception("Failed unexpectedly when adding a sticker!")
        raise

    return success


def create_set(update, context):
    user = update.effective_user
    bot = context.bot
    message = update.message
    sticker_set_name = _sticker_set_name(update, context)
    sticker_set_title = message.text
    filepath_png = context.user_data['photo_filepath']
    emojis = context.user_data['emojis']

    try:
        with open(filepath_png, 'rb') as png_sticker:
            success = bot.create_new_sticker_set(
                user['id'],
                sticker_set_name,
                sticker_set_title,
                png_sticker,
                emojis)

        if success:
            message.reply_text(text=f"Created a new sticker set with your sticker!", quote=False)
            # TODO: Reply with the sticker
        else:
            # Not sure if we ever end up here as the call seems to throw exceptions instead
            message.reply_text(text=f"Server reported failure when attempting to create sticker set!")
    except BadRequest as exception:
        if exception.message == "Sticker set name is already occupied":
            message.reply_text(f"You have already created a personal sticker set. Currently you can only have one!")
        else:
            logger.exception("Failed unexpectedly when creating sticker set!")
        success = False
    finally:
        temporary_directory = context.user_data['photo_temporary_directory']
        temporary_directory.cleanup()
        del context.user_data['photo_temporary_directory']
        del context.user_data['photo_filepath']
        del context.user_data['emojis']

    # TODO: Check if the channel has a dedicated set

    return ConversationHandler.END


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('stickers', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(add_sticker_start, pattern=f"^{State.ADD_STICKER_START}$"),
            ],
        State.ADD_STICKER_PHOTO: [
            MessageHandler(Filters.photo, add_sticker_photo),
            ],
        State.ADD_STICKER_EMOJI: [
            MessageHandler(Filters.text, add_sticker_emoji),
            ],
        State.CREATE_SET: [
            MessageHandler(Filters.text, create_set),
            ],
    },
    fallbacks=[CommandHandler('stickers', start)]
)
