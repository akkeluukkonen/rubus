"""
Managing Telegram sticker sets and stickers using the bot interface.
"""
import enum
import hashlib
import logging
import os
import tempfile

from PIL import Image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler
from telegram.ext import Filters
from telegram.error import BadRequest

from rubus import helper


logger = logging.getLogger('rubus')

STICKER_DIMENSION_SIZE_PIXELS = 512  # Per Telegram sticker requirements


class State(enum.IntEnum):
    """States for the ConversationHandler

    In a State the handler is waiting for the next message to arrive.
    The performed actions may depend on the message content.
    """
    MENU = enum.auto()
    ADD_STICKER_SET_TITLE = enum.auto()
    ADD_STICKER_PHOTO = enum.auto()
    ADD_STICKER_EMOJI = enum.auto()


class Command(enum.IntEnum):
    """Commands for the ConversationHandler

    Can be directly used as a value for the CallbackQueryHandler from the InlineKeyboard.
    """
    ADD_STICKER_START = enum.auto()


def start(update, context):  # pylint: disable=unused-argument
    """Present the user all available sticker configuration options"""
    keyboard = [
        [InlineKeyboardButton("Add sticker to channel set", callback_data=Command.ADD_STICKER_START)],
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select configuration option:", reply_markup=reply_markup)
    return State.MENU


def _sticker_set_name(update, context):
    """Note that the name is different from the title, which is visible to the users"""
    if context.chat_data.get('sticker_set'):
        logger.debug(f"Found a channel default sticker set {context.chat_data['sticker_set']}")
        return context.chat_data['sticker_set']

    # Create a unique sticker set per each user and channel
    chat, user = update.effective_chat, update.effective_user
    # Calculate a hash for privacy as it is visible in t.me/stickers
    hash_object = hashlib.md5(f"{chat.id}{user.id}".encode('utf-8'))
    prefix = hash_object.hexdigest()

    # The name must end in _by_<bot_username> per Telegram rules
    bot = context.bot
    bot_user_account = bot.get_me()
    sticker_set_name = f"{prefix}_by_{bot_user_account['username']}"
    logger.debug(f"Formed sticker set name '{sticker_set_name}'")
    return sticker_set_name


def _sticker_set_exists(update, context, sticker_set_name=None):
    if sticker_set_name is None:
        sticker_set_name = _sticker_set_name(update, context)

    try:
        context.bot.get_sticker_set(sticker_set_name)
    except BadRequest as exception:
        if exception.message == "Stickerset_invalid":
            return False

    return True


def add_sticker_start(update, context):  # pylint: disable=unused-argument
    """Start routine of adding a sticker to an existing set

    The sticker will require a photo as well as a corresponding emoji,
    which will be gathered from the user in the next steps.

    If the channel has no dedicated sticker set yet, one will be created during this process.
    """
    query = update.callback_query

    if not _sticker_set_exists(update, context):
        query.message.edit_text(
            "No sticker sets were available. Send the name you want to use for creating one.")
        return State.ADD_STICKER_SET_TITLE

    query.message.edit_text("Send me the photo for the sticker")
    return State.ADD_STICKER_PHOTO


def add_sticker_set_title(update, context):
    """Get a name for the sticker set as seen by the users"""
    message = update.message
    context.user_data['sticker_set_title'] = message.text

    message.reply_text("Send me the photo for the sticker to create the set with", quote=False)
    return State.ADD_STICKER_PHOTO


def _resize_and_convert_to_png(update, context, temporary_directory):
    # A photo can have multiple PhotoSize elements tied together
    # but we want to use the largest one for possible resize operations
    photos = update.message.photo
    photo = max(photos, key=lambda x: x.file_size)
    file = context.bot.get_file(photo.file_id)
    # The file is stored as .jpg on Telegram servers
    # so we need to resize and convert it manually to .png
    filepath_jpg = os.path.join(temporary_directory, "photo.jpg")
    file.download(custom_path=filepath_jpg)
    image_jpg = Image.open(filepath_jpg)
    # At least one dimension must be STICKER_DIMENSION_SIZE_PIXELS
    # and neither dimension can exceed this value
    longest_dimension = max(image_jpg.size)
    ratio = STICKER_DIMENSION_SIZE_PIXELS / longest_dimension
    width_new = int(image_jpg.size[0] * ratio)
    height_new = int(image_jpg.size[1] * ratio)
    image_resized = image_jpg.resize((width_new, height_new))

    filepath_png = os.path.join(temporary_directory, "photo.png")
    image_resized.save(filepath_png)
    return filepath_png


def add_sticker_photo(update, context):
    """Get a photo from the user and convert it to the required format"""
    with tempfile.TemporaryDirectory() as temporary_directory:
        filepath_png = _resize_and_convert_to_png(update, context, temporary_directory)
        with open(filepath_png, 'rb') as png_sticker:
            file = context.bot.upload_sticker_file(update.effective_user['id'], png_sticker)

    context.user_data['sticker_file_id'] = file.file_id
    update.message.reply_text("Send me the emojis (1 to 3) matching the photo")
    return State.ADD_STICKER_EMOJI


def add_sticker_emoji(update, context):
    """Get 1 to 3 emoji(s) from the user and add a new sticker to the current set"""
    user = update.effective_user
    bot = context.bot
    sticker_set_name = _sticker_set_name(update, context)
    sticker_set_title = context.user_data.get('sticker_set_title')
    sticker_file_id = context.user_data['sticker_file_id']
    message = update.message
    emojis = message.text

    try:
        if sticker_set_title:
            success = bot.create_new_sticker_set(
                user['id'], sticker_set_name, sticker_set_title, sticker_file_id, emojis)
            context.chat_data['sticker_set'] = sticker_set_name
        else:
            success = bot.add_sticker_to_set(user['id'], sticker_set_name, sticker_file_id, emojis)
    except BadRequest as exception:
        if exception.message == "Invalid sticker emojis":
            message.reply_text("Invalid emojis. Send me new ones.")
            return State.ADD_STICKER_EMOJI

        if exception.message == "Peer_id_invalid":
            message.reply_text(
                "You need to send me /start privately. "
                "Otherwise, I'm unable to create or access sticker sets owned by you. "
                "\n\nSend me the emojis again after you've messaged me.")
            return State.ADD_STICKER_EMOJI


        logger.exception("Failed unexpectedly when adding stickers!")
        success = False

    if success:
        sticker_set = bot.get_sticker_set(sticker_set_name)
        sticker = sticker_set.stickers[-1]  # Latest sticker will be last in the list
        # Note that sticker.file_id is different from sticker_file_id
        # Telegram uses a different id for a sticker included in a set for some reason
        message.reply_sticker(sticker.file_id, quote=False)
    else:
        message.reply_text("Unexpected failure. Please try again and contact the developer.", quote=False)

    del context.user_data['sticker_file_id']
    if context.user_data.get('sticker_set_title'):
        del context.user_data['sticker_set_title']

    return ConversationHandler.END


handler_conversation = ConversationHandler(
    entry_points=[CommandHandler('stickers', start)],
    states={
        State.MENU: [
            CallbackQueryHandler(add_sticker_start, pattern=f"^{Command.ADD_STICKER_START}$"),
            ],
        State.ADD_STICKER_SET_TITLE: [
            MessageHandler(Filters.text, add_sticker_set_title),
            ],
        State.ADD_STICKER_PHOTO: [
            MessageHandler(Filters.photo, add_sticker_photo),
            ],
        State.ADD_STICKER_EMOJI: [
            MessageHandler(Filters.text, add_sticker_emoji),
            ],
    },
    fallbacks=[MessageHandler(Filters.all, helper.confused)]
)
