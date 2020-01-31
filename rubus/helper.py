"""
General helper functions which can be shared between multiple modules.
"""
import collections
import importlib.resources
import json
import logging
import sqlite3

from telegram.ext import ConversationHandler


logger = logging.getLogger('rubus')


def config_load():
    """Load stored configuration from disk

    Configuration should be stored as JSON along with the module files.

    :return: Dictionary of the configuration
    """
    config_text = importlib.resources.read_text("rubus", "config.json")
    data = json.loads(config_text)
    return data


def cancel(update, context):  # pylint: disable=unused-argument
    """Handler for canceling current operation in ConversationHandler

    Automatically ends the conversation.
    """
    query = update.callback_query
    query.message.edit_text("Canceled")
    return ConversationHandler.END


def confused(update, context):  # pylint: disable=unused-argument
    """Handler for unkown states in ConversationHandler

    Automatically ends the conversation to avoid weird situations.
    """
    message = update.message
    message.reply_text(
        "Sorry, I'm confused and didn't understand what you wanted me to do.\n"
        "Cancelling current operation.")
    return ConversationHandler.END


def group_elements(flat_list, amount_per_group):
    """Create list of tuples from elements in a flat list

    The last group may be underfilled if the iterator does not split evenly into the requested pairs,
    therefore resulting in a different result compared to using itertools.zip_longest.
    """
    grouped = list(zip(*[iter(flat_list)] * amount_per_group))
    # We still need to add the remaining elements if any
    remaining = len(flat_list) % amount_per_group
    if remaining:
        grouped.append(tuple(flat_list[-remaining:]))
    return grouped


# Queue objects will be used for ensuring for multi-thread communications to
# ensure that only a single thread is accessing the database to avoid errors.
Query = collections.namedtuple('Query', ['statement', 'args'])
Result = collections.namedtuple('Result', ['statement', 'args', 'rows'])


def database_worker(database_filepath, queries, results):
    """All database queries should be submitted through this worker"""
    logger.debug(f"Connecting to {database_filepath}")
    # Set isolation_level=None for autocommit mode as we are running the
    # database through a single thread, thus making db management easier.
    conn = sqlite3.connect(database_filepath, isolation_level=None)
    cursor = conn.cursor()
    while True:
        query = queries.get()

        try:
            rows = cursor.execute(query.statement, query.args).fetchall()
            results.put(Result(query.statement, query.args, rows))
        except (sqlite3.OperationalError, sqlite3.ProgrammingError):
            logger.exception("SQLite exception during transaction!")
            results.put(None)


def database_query(queries, results, statement, *args):
    """Request a query from the database"""
    queries.put(Query(statement, args))
    # Block while waiting for the results...
    result = results.get()
    if result is None:
        raise RuntimeError("Error in transaction!")
    return result.rows


def database_query_single(queries, results, statement, *args):
    """Request query returning only a single row or element

    The caller is responsible of expecting what format is returned.
    """
    rows = database_query(queries, results, statement, *args)
    if not rows:
        return None

    # Even if only one row is returned, it will be in a list per the SQLite interface
    row = rows[0]
    if len(row) == 1:
        # Return exactly the only element for easier parsing for the caller
        return row[0]

    return row
