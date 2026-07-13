import yaml  # type:ignore
import random
from datetime import date, timedelta, datetime
from psycopg2.extras import execute_values

from api.db.connection import get_store_connection, release_connection

with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)

with open("config/menu.yaml", "r") as f:
    menu = yaml.safe_load(f)


# Guarantee that dates for menu items are parsed correctly
for item in menu["items"]:
    if isinstance(item["added"], str):
        item["added"] = datetime.strptime(item["added"], "%Y-%m-%d").date()


RUSH_CURVE = {
    0: 0.1,  1: 0.05, 2: 0.05, 3: 0.05, 4: 0.1,  5: 0.2,
    6: 0.6,  7: 0.9,  8: 0.9,  9: 0.7,  10: 0.6, 11: 0.8,
    12: 1,   13: 0.8, 14: 0.6, 15: 0.5, 16: 0.8, 17: 0.9,
    18: 0.7, 19: 0.5, 20: 0.3, 21: 0.2, 22: 0.1, 23: 0.1
}

BASE_VOLUME = {1: 80, 2: 140, 3: 220, 4: 400}
weights = [5, 10, 25, 30, 25, 10, 5]

RANDOMNESS = {
    1: {"values": [-10, -8, -2, 0, 2, 6, 10], "weights": weights},
    2: {"values": [-30, -15, -5, 0, 5, 15, 30], "weights": weights},
    3: {"values": [-60, -30, -10, 0, 10, 30, 60], "weights": weights},
    4: {"values": [-100, -50, -20, 0, 20, 50, 100], "weights": weights}
}

START_DATE = date(2026, 5, 20)

HOURS_AVAILABLE = {
    "breakfast": [4, 12],
    "lunch": [10, 22],
    "all_day": [0, 24],
    "chicken": [9, 22],
}

WEEKDAY_MULTIPLIER = {
    0: 0.9, 1: 1.0, 2: 1.0, 3: 1.2, 4: 1.2, 5: 0.8, 6: 0.7
}

# Pre-calculates date attributes
SIMULATION_DAYS = []
for day_idx in range(42):
    sim_date = START_DATE + timedelta(days=day_idx)
    SIMULATION_DAYS.append({
        "date": sim_date,
        "int": sim_date.weekday()
    })


for store in stores["stores"]:

    store_id = store["id"]
    level = int(store["level"])
    hours = store["hours"]

    if hours == "24/7": min_max_hours = [0, 24]
    elif hours == "5am-11pm": min_max_hours = [5, 23]
    else:
        print(f"Hours unknown for {store_id}, skipping.")
        continue

    print(f"[{store_id}] Establishing transaction connection...")
    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        # Accumulate the ENTIRE 6-week run for this store in memory, so we
        # only round-trip to Neon once (via execute_values below) instead of
        # once per day
        store_sales_batch = []

        for day_data in SIMULATION_DAYS:
            sim_date = day_data["date"]
            weekday_int = day_data["int"]

            # Simulates random days by creating a random offset
            random_offset = random.choices(
                RANDOMNESS[level]["values"],
                weights=RANDOMNESS[level]["weights"]
            )[0]

            day_base_target = BASE_VOLUME[level] + random_offset

            for hour in range(min_max_hours[0], min_max_hours[1]):

                event_count = max(1, round(RUSH_CURVE[hour] *
                    WEEKDAY_MULTIPLIER[weekday_int] * day_base_target))

                available_items = []
                for item in menu["items"]:
                    availability = HOURS_AVAILABLE[item["time_of_day"]]
                    if (item["active"] and
                            item["added"] <= sim_date and
                            hour in range(availability[0], availability[1])):
                        available_items.append(item)

                if not available_items:
                    continue

                popularity_weights = [i["popularity"] for i in available_items]

                for _ in range(event_count):
                    item = random.choices(available_items,
                                          weights=popularity_weights)[0]
                    sale_days = item.get("sale_days", [])
                    sale_price = item.get("sale_price")

                    if weekday_int in sale_days and sale_price is not None:
                        price = item["sale_price"]
                    else:
                        price = item["price"]

                    quantity = random.choices([1, 2, 3],
                                              weights=[0.7, 0.2, 0.1])[0]

                    event_time = datetime(
                        sim_date.year, sim_date.month, sim_date.day,
                        hour, random.randint(0, 59), random.randint(0, 59)
                    )

                    store_sales_batch.append(
                        (item["id"], quantity, price, event_time))

        # Single INSERT (large page_size to minimize round-trips) + single
        # commit for the entire store, instead of one round-trip per day.
        if store_sales_batch:
            execute_values(cursor, """
                INSERT INTO sales_events (item_id, quantity, price, created_at)
                VALUES %s
            """, store_sales_batch, page_size=10000)

        connection.commit()
        print(f"[{store_id}] Successfully persisted {len(store_sales_batch)} " \
              "rows across 6 weeks.")

    except Exception as e:
        connection.rollback()
        print(f"[{store_id}] FAILED: {e}")

    finally:
        cursor.close()
        release_connection(connection)
