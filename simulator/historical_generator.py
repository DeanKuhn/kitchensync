# Generates fake historical data (different on store level)


import yaml # type:ignore
import random
from datetime import date, timedelta, datetime
from psycopg2.extras import execute_values

from api.db.connection import get_store_connection, release_connection


with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)

with open("config/menu.yaml", "r") as f:
    menu = yaml.safe_load(f)


RUSH_CURVE = {
    0: 0.1,
    1: 0.05,
    2: 0.05,
    3: 0.05,
    4: 0.1,
    5: 0.2,
    6: 0.6,
    7: 0.9,
    8: 0.9,
    9: 0.7,
    10: 0.6,
    11: 0.8,
    12: 1,
    13: 0.8,
    14: 0.6,
    15: 0.5,
    16: 0.8,
    17: 0.9,
    18: 0.7,
    19: 0.5,
    20: 0.3,
    21: 0.2,
    22: 0.1,
    23: 0.1
}

BASE_VOLUME = {
    1: 50,
    2: 100,
    3: 200,
    4: 400
}

RANDOMNESS = {
    1: {"values": [-10, -8, -2, 0, 2, 6, 10], "weights": [10, 15, 20, 10, 20, 15, 10]},
    2: {"values": [-30, -15, -5, 0, 5, 15, 30], "weights": [10, 15, 20, 10, 20, 15, 10]},
    3: {"values": [-60, -30, -10, 0, 10, 30, 60], "weights": [10, 15, 20, 10, 20, 15, 10]},
    4: {"values": [-100, -50, -20, 0, 20, 50, 100], "weights": [10, 15, 20, 10, 20, 15, 10]}
}

START_DATE = date(2026, 1, 1)

HOURS_AVAILABLE = {
    "breakfast": [4, 11],
    "lunch": [10, 22],
    "all_day": [0, 24],
    "chicken": [9, 22]
}


for store in stores["stores"]:

    store_id = store["id"]
    level = int(store["level"])
    hours = store["hours"]

    if hours == "24/7": min_max_hours = [0, 24]
    elif hours == "5am-11pm": min_max_hours = [5, 23]
    else:
        print(f"Hours unknown for {store_id}, skipping.")
        continue

    # One connectoin checkout for the entire store
    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        for day in range(90):

            sim_date = START_DATE + timedelta(days=day)

            for hour in range(min_max_hours[0], min_max_hours[1]):

                event_count = max(0, round(RUSH_CURVE[hour] *
                                    (BASE_VOLUME[level] +
                                    random.choices(RANDOMNESS[level]["values"],
                                        weights=RANDOMNESS[level]["weights"])[0])))

                available_items = []

                for item in menu["items"]:
                    category = item["category"]
                    availability = HOURS_AVAILABLE[category]

                    if (item["active"] == True and
                        item["added"] <= sim_date and
                        hour in range(availability[0], availability[1])):
                        available_items.append(item)

                if not available_items: continue

                # Build the batch for this hour
                batch = []

                for _ in range(event_count):

                    item = random.choice(available_items)

                    price = random.choices([item["price"], item["sale_price"]],
                                            weights=[0.8, 0.2])[0]

                    quantity = random.choices([1, 2, 3],
                                            weights=[0.7, 0.2, 0.1])[0]

                    event_time = datetime(
                        sim_date.year,
                        sim_date.month,
                        sim_date.day,
                        hour,
                        random.randint(0, 59),
                        random.randint(0, 59)
                    )

                    batch.append((item["id"], quantity, price, event_time))

                # One INSERT for the entire hour's worth of events
                execute_values(cursor, """
                    INSERT INTO sales_events (item_id, quantity, price, created_at)
                    VALUES %s
                """, batch)

            # Commit once per day, not once per event
            connection.commit()
            print(f"[{store_id}] Day {day + 1}/90 ({sim_date}) complete")

    except Exception as e:
        connection.rollback()
        print(f"[{store_id}] FAILED: {e}")

    finally:
        cursor.close()
        release_connection(connection)