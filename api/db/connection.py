# Job of this file:
# Take the NEON_DATABASE_URL from the .env vile and return a working database
# connection that other parts of the app can use.


import os
import psycopg2
from dotenv import load_dotenv # type:ignore


# Loads variables from .env into the environment
load_dotenv()


def get_connection():

    # Get the database url from the .env file loaded
    database_url = os.getenv("NEON_DATABASE_URL")

    # Raise error if the os can't find anything (gives back None)
    if not database_url:
        raise ValueError("NEON_DATABASE_URL is not set in the .env file.")

    # Returns a psycopg2 connection
    return psycopg2.connect(database_url)


def get_store_connection(store_id: str):

    # Call get_connection() to get a regular connection
    connection = get_connection()

    # On this connection, run an SQL command that sets the search_path
    # This uses a psycopg2 cursor, which is the object you use to execute SQL
    # on a connection
    cursor = conn.connection() # type:ignore
    cursor.execute(f"SET search_path TO {store_id}, public;")
    cursor.close()

    # What this actually does:
    # The Neon database has many schemas since there are many stores
    # Each schema has it's own imformation, such as custom sales data.
    #
    # If a connection without a search_path is opened and
    # SELECT * FROM sales_events;
    # is ran, Neon won't know which schema to open.
    #
    # search_path allows every SQL execution or query on a schema using this
    # specific connection to add the {store_id} to the beginning of the
    # wanted rows.
    #
    # So, for example, if I did the previous query:
    # SELECT * FROM sales_events;
    # with the proper search_path configured in the connection, it would
    # actually do this:
    # SELECT * FROM {store_id}.sales_events;
    # This saves both time and a lot of extra text in connection requests.

    # Returns the connection to the appropriate store's schema
    return connection