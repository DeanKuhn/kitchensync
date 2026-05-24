import yaml # type:ignore
import random
import time
import datetime
import threading
import requests
import pandas as pd
from sqlalchemy import text # type:ignore

from ml.features import get_snowflake_engine


with open("config/stores.yaml") as f:
    stores = yaml.safe_load(f)

with open("config/menu.yaml") as f:
    menu = yaml.safe_load(f)


TIME_SCALE = 120
API_BASE_URL = "http://localhost:8000"
TICK_INTERVAL = 2
START_TIME = datetime.datetime(2026, 2, 12, 0, 0, 0)

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
    1: 80,
    2: 140,
    3: 220,
    4: 400
}

RANDOMNESS = {
    1: {"values": [-10, -8, -2, 0, 2, 6, 10], "weights": [5, 10, 25, 30, 25, 10, 5]},
    2: {"values": [-30, -15, -5, 0, 5, 15, 30], "weights": [5, 10, 25, 30, 25, 10, 5]},
    3: {"values": [-60, -30, -10, 0, 10, 30, 60], "weights": [5, 10, 25, 30, 25, 10, 5]},
    4: {"values": [-100, -50, -20, 0, 20, 50, 100], "weights": [5, 10, 25, 30, 25, 10, 5]}
}

HOURS_AVAILABLE = {
    "breakfast": [4, 12],
    "lunch": [10, 22],
    "all_day": [0, 24],
    "chicken": [9, 22],
    "appetizers": [9, 22],
    "sides": [9, 22]
}

WEEKDAY_MULTIPLIER = {
    "Sunday": 0.7,
    "Monday": 0.9,
    "Tuesday": 1.0,
    "Wednesday": 1.0,
    "Thursday": 1.2,
    "Friday": 1.2,
    "Saturday": 0.8
}


active_batches = {store["id"]: [] for store in stores["stores"]}
batch_lock = threading.Lock()

predictions = {}
predictions_lock = threading.Lock()


def sell_from_batch(store_id, item_id, quantity):

    with batch_lock:
        for b in active_batches[store_id]:
            if b["item_id"] == item_id:
                b["quantity"] -= quantity
                if b["quantity"] <= 0:
                    active_batches[store_id] = [b for b in active_batches[store_id]
                        if b["quantity"] > 0]
                break


def fire_sale(store_id, item, sim_now):

    url = API_BASE_URL + f"/events/{store_id}/sales"

    item_id = item["id"]
    normal_price = item["price"]
    sale_price = item["sale_price"]
    price = random.choices([normal_price, sale_price], weights=[0.8, 0.2])[0]
    quantity = random.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]

    try:
        requests.post(url,
            json={"item_id": item_id,
                  "quantity": quantity,
                  "price": price,
                  "created_at": sim_now.isoformat()})

        sell_from_batch(store_id, item_id, quantity)

        print(f"[{store_id}] SALE: {item_id} x{quantity} @ ${price:.2f} | {sim_now}")
    except Exception as e:
        print(f"POST request failed, {e}")


def fire_waste(store_id, item_id, quantity, sim_now):

    url = API_BASE_URL + f"/events/{store_id}/waste"

    try:
        requests.post(url,
            json={"item_id": item_id,
                  "quantity": quantity,
                  "reason": "expired",
                  "created_at": sim_now.isoformat()})
        print(f"[{store_id}] WASTE: {item_id} x{quantity} | {sim_now}")
    except Exception as e:
        print(f"POST request failed, {e}")


def produce_batch(store_id, item, quantity, sim_now):

    item_id = item["id"]
    item_hold_time = datetime.timedelta(hours=item["hold_time"])
    expiration_time = sim_now + item_hold_time

    with batch_lock:
        active_batches[store_id].append({"item_id": item_id,
                                        "quantity": quantity,
                                        "expiration_time": expiration_time})


def check_expired_batches(store_id, sim_now):

      with batch_lock:
          expired = [b for b in active_batches[store_id]
                     if b["expiration_time"] <= sim_now]
          active_batches[store_id] = [b for b in active_batches[store_id]
                                      if b["expiration_time"] > sim_now]

      for batch in expired:
          fire_waste(store_id, batch["item_id"], batch["quantity"], sim_now)


def refresh_production_plan():

    engine = get_snowflake_engine()

    while True:
        # Fetch the latest production plan for all stores and items
        query = text("""
            select
                store_id,
                item_id,
                predicted_units

            from MARTS.PREDICTIONS
            where predicted_at = (select max(predicted_at) from MARTS.PREDICTIONS)
        """)

        df = pd.read_sql(query, engine)
        df.columns = df.columns.str.lower()

        # Rebuild the shared predictions dictionary under lock
        # so store threads always see a consistent snapshot
        with predictions_lock:
            for _, row in df.iterrows():
                predictions[(row["store_id"], row["item_id"])] = \
                    row["predicted_units"]

        print(f"[PREDICTIONS] Refreshed {len(df)} store/item predictions")

        # Wait 2 real minutes before refreshing again
        time.sleep(120)


def simulate_store(store):

    store_id = store["id"]
    level = int(store["level"])
    hours = store["hours"]

    sim_now = START_TIME

    while True:
        # Sim now increments every 2 seconds real time, 2 minutes simulation time
        sim_now += datetime.timedelta(seconds=TICK_INTERVAL * TIME_SCALE)
        hour = sim_now.hour
        weekday = sim_now.strftime("%A")

        # Check if the store is not open 24 hours
        if hours == "5am-11pm" and (hour < 5 or hour >= 23):
            time.sleep(TICK_INTERVAL)
            continue

        # Determine event count for each store to create simulated sales
        event_count = max(1, round(
            RUSH_CURVE[hour] *
            WEEKDAY_MULTIPLIER[weekday] *
            (BASE_VOLUME[level] + random.choices(
                RANDOMNESS[level]["values"],
                weights=RANDOMNESS[level]["weights"]
            )[0])
        ))

        # Divide by ticks per sim hour so event_count scales correctly
        # regardless of TIME_SCALE
        ticks_per_hour = 3600 / (TICK_INTERVAL * TIME_SCALE)
        event_count /= ticks_per_hour

        # Determine available items based on time and category
        available_items = []

        for item in menu["items"]:
            category = item["category"]
            availability = HOURS_AVAILABLE[category]

            if (item["active"] == True and
                item["added"] <= sim_now.date() and
                hour in range(availability[0], availability[1])):
                available_items.append(item)

        # If no items are available, we simply skip
        if not available_items:
            time.sleep(TICK_INTERVAL)
            continue

        # ... and then take the float and use random.random, since many times
        # the number may be small and round to 0 anyways, like 0.13
        if random.random() < event_count:

            # Choose item based on item popularity
            item = random.choices(
                available_items,
                weights=[i["popularity"] for i in available_items]
            )[0]

            fire_sale(store_id, item, sim_now)

        # --- PRODUCTION LOGIC ---

        # For each available item, check the predicted amounts in the
        # predictions dictionary
        for item in available_items:
            key = (store_id, item["id"])
            with predictions_lock:
                predicted = predictions.get(key, 0)

            # Also, check if this is already being produced (meaning it's
            # been made but hasn't expired yet)
            with batch_lock:
                already_producing = any(
                    b["item_id"] == item["id"]
                    for b in active_batches[store_id]
                )

            # If there are more than 0 predicted to sell and the batch
            # has not expired, create the new batch
            if predicted > 0 and not already_producing:
                produce_batch(store_id, item, predicted, sim_now)

        # Check expired batches, and wait two minutes
        # for the simulator to fire again
        check_expired_batches(store_id, sim_now)
        time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    refresh_thread = threading.Thread(
        target=refresh_production_plan, daemon=True)
    refresh_thread.start()

    threads = []

    for store in stores["stores"]:
        t = threading.Thread(target=simulate_store, args=(store,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()