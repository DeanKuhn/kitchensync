import asyncio
import subprocess
import httpx
import yaml # type:ignore
import random
import numpy as np
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import text # type:ignore

from ml.features import get_snowflake_engine

# --- LOAD CONFIGS ---
with open("config/stores.yaml") as f:
    stores = yaml.safe_load(f)

with open("config/menu.yaml") as f:
    menu = yaml.safe_load(f)

# Ensure proper date parsing for cold-start logic
for item in menu["items"]:
    if isinstance(item["added"], str):
        item["added"] = datetime.strptime(item["added"], "%Y-%m-%d").date()


# --- CONFIGURATION ---
TIME_SCALE = 20
API_BASE_URL = "http://localhost:8000"
TICK_INTERVAL = 1
START_TIME = datetime.now()

RUSH_CURVE = {
    0: 0.1,  1: 0.05, 2: 0.05, 3: 0.05, 4: 0.1,  5: 0.2,
    6: 0.6,  7: 0.9,  8: 0.9,  9: 0.7,  10: 0.6, 11: 0.8,
    12: 1,   13: 0.8, 14: 0.6, 15: 0.5, 16: 0.8, 17: 0.9,
    18: 0.7, 19: 0.5, 20: 0.3, 21: 0.2, 22: 0.1, 23: 0.1
}

BASE_VOLUME = {1: 80, 2: 140, 3: 220, 4: 400}
WEIGHTS = [5, 10, 25, 30, 25, 10, 5]

RANDOMNESS = {
    1: {"values": [-10, -8, -2, 0, 2, 6, 10], "weights": WEIGHTS},
    2: {"values": [-30, -15, -5, 0, 5, 15, 30], "weights": WEIGHTS},
    3: {"values": [-60, -30, -10, 0, 10, 30, 60], "weights": WEIGHTS},
    4: {"values": [-100, -50, -20, 0, 20, 50, 100], "weights": WEIGHTS}
}

HOURS_AVAILABLE = {
    "breakfast": [4, 12],
    "lunch": [10, 22],
    "all_day": [0, 24],
    "chicken": [9, 22],
}

WEEKDAY_MULTIPLIER = {
    0: 0.9, 1: 1.0, 2: 1.0, 3: 1.2, 4: 1.2, 5: 0.8, 6: 0.7
}

# Global state for prescriptive targets:
# (store_id, slot_index, item_id) -> target_qty
production_targets = {}


# --- UTILITY CLASSES ---
class SimClock:
    def __init__(self, start_time, time_scale):
        self.start_time = start_time
        self.time_scale = time_scale
        # Record exactly when the simulation started in the real world
        self.real_start = asyncio.get_event_loop().time()

    def now(self):
        # Returns the current simulation datetime
        real_elapsed = asyncio.get_event_loop().time() - self.real_start
        sim_elapsed_seconds = real_elapsed * self.time_scale
        return self.start_time + timedelta(seconds=sim_elapsed_seconds)

class StoreState:
    def __init__(self, store_id):
        self.store_id = store_id
        # inventory format: { "ITEM_ID": [batch1, batch2, ...] }
        self.inventory = {}
        # progress format: { "ITEM_ID": [batch1, batch2, ...] }
        self.in_progress = {}

    def start_cooking(self, item_id, quantity, ready_at, expires):
        # Starts cooking future batch of food
        if item_id not in self.in_progress:
            self.in_progress[item_id] = []
        self.in_progress[item_id].append({"quantity": quantity,
                                          "ready_at": ready_at,
                                          "expires": expires})

    def promote_ready_batches(self, sim_now, store_id):
        for item_id, batches in self.in_progress.items():
            if item_id not in self.inventory:
                self.inventory[item_id] = []
            for b in batches:
                if b["ready_at"] <= sim_now:
                    self.inventory[item_id].append({"quantity": b["quantity"],
                                                    "expires": b["expires"]})
                    # print(f"[{store_id}] FOOD READY! {item_id} x{b['quantity']} | "
                    #       f"ready at {sim_now.strftime('%H:%M')} | "
                    #       f"expires {b['expires'].strftime('%H:%M')}")
            self.in_progress[item_id] = \
                [b for b in batches if b["ready_at"] > sim_now]

    def consume(self, item_id, quantity):
        # Removes food when sold, returns actual quantity sold
        if item_id not in self.inventory or not self.inventory[item_id]:
            return 0

        sold = 0
        while quantity > 0 and self.inventory[item_id]:
            batch = self.inventory[item_id][0] # FIFO
            if batch["quantity"] <= quantity:
                sold += batch["quantity"]
                quantity -= batch["quantity"]
                self.inventory[item_id].pop(0)
            else:
                batch["quantity"] -= quantity
                sold += quantity
                quantity = 0
        return sold

    def get_total_quantity(self, item_id):
        return sum(batch["quantity"] for batch in
                   self.inventory.get(item_id, []))

    def get_in_progress_quantity(self, item_id):
        return sum(batch["quantity"] for batch in
                   self.in_progress.get(item_id, []))

    def inventory_summary(self):
        return {
            item_id: self.get_total_quantity(item_id)
            for item_id in self.inventory
            if self.get_total_quantity(item_id) > 0
        }


# --- API FIRING FUNCTIONS ---
async def fire_sale(client, store_id, item_id, quantity, price, sim_now):
    url = f"{API_BASE_URL}/events/{store_id}/sales"
    payload = {
        "item_id": item_id,
        "quantity": int(quantity),
        "price": float(price),
        "created_at": sim_now.isoformat()
    }
    try:
        await client.post(url, json=payload, timeout=5.0)
    except Exception as e:
        print(f"[{store_id}] SALE ERROR: {e}")


async def fire_waste(client, store_id, item_id, quantity, sim_now):
    url = f"{API_BASE_URL}/events/{store_id}/waste"
    payload = {
        "item_id": item_id,
        "quantity": int(quantity),
        "created_at": sim_now.isoformat()
    }
    try:
        await client.post(url, json=payload, timeout=5.0)
        print(f"[{store_id}] WASTE: {item_id} x{quantity} " \
              f"| {sim_now.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[{store_id}] WASTE ERROR: {e}")


async def fire_stockout(client, store_id, item_id, quantity_requested, sim_now):
    url = f"{API_BASE_URL}/events/{store_id}/stockout"
    payload = {
        "item_id": item_id,
        "quantity_requested": int(quantity_requested),
        "created_at": sim_now.isoformat()
    }
    try:
        await client.post(url, json=payload, timeout=5.0)
        print(f"[{store_id}] STOCKOUT: {item_id} x{quantity_requested} " \
              f"requested | {sim_now.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"[{store_id}] STOCKOUT ERROR: {e}")


# --- BACKGROUND TASKS ---
async def refresh_targets_task():

    while True:
        # Technically a refresh, but since this is a weekly snapshot it is just
        # loaded in once and left (in real world, would be ran weekly)

        engine = get_snowflake_engine()
        global production_targets

        try:
            print("[SIMULATOR] Loading 15-min production targets from Snowflake...")
            query = text("""
                SELECT store_id, slot_index, item_id, predicted_units
                FROM MARTS.PREDICTIONS
            """)

            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, lambda: pd.read_sql(query, engine))
            df.columns = df.columns.str.lower()

            new_targets = {}
            for _, row in df.iterrows():
                # Key: (store_id, slot_index, item_id)
                key = (row['store_id'], int(row['slot_index']), row['item_id'])
                new_targets[key] = float(row['predicted_units'])

            production_targets = new_targets
            print(f"[SIMULATOR] Loaded {len(production_targets)} prescriptive targets.")
        except Exception as e:
            print(f"[TARGETS ERROR] {e}")

        await asyncio.sleep(86400)


# --- SIMULATION FUNCTION ---
async def simulate_store(config, clock, client):

    store_id = config["id"]
    level = int(config["level"])
    store_hours = config["hours"]

    state = StoreState(store_id)
    print(f"[{store_id}] Starting | Level {level} | {store_hours}")

    # Start off with default amounts of food
    if store_hours != "5am-11pm":
        seed_sim_now = clock.now()
        seed_slot_idx = ((seed_sim_now.weekday() * 96) + (seed_sim_now.hour * 4) +
                        (seed_sim_now.minute // 15)) % 672

        for item in menu["items"]:
            if not item["active"]: continue
            seed_look_ahead = int(item["hold_time"] * 4)
            seed_demand = sum(production_targets.get(
                (store_id, (seed_slot_idx + i) % 672, item["id"]), 0)
                    for i in range(seed_look_ahead))

            if seed_demand > 0:
                expires = seed_sim_now + timedelta(hours=item["hold_time"])
                state.inventory[item["id"]] = [{"quantity": seed_demand,
                                                "expires": expires}]

    last_hour = -1
    last_slot_idx = -1
    hour_sales = hour_cooked = hour_wasted = hour_stockouts = 0

    while True:
        sim_now = clock.now()
        hour = sim_now.hour
        weekday_int = sim_now.weekday()

        # Check for batches to promote
        state.promote_ready_batches(sim_now, store_id)

        # Hourly "heartbeat" check
        if hour != last_hour:
            if last_hour != -1:
                shelf = ", ".join(
                    f"{k}:{v}" for k, v in state.inventory_summary().items()
                )
                print(
                    f"\n[{store_id}] ── {sim_now.strftime('%a %b %d %H:%M')} | "
                    f"sold={hour_sales} cooked={hour_cooked} "
                    f"wasted={hour_wasted} stockouts={hour_stockouts}\n"
                    f"           shelf: {shelf or 'empty'}\n"
                )
            last_hour = hour
            hour_sales = hour_cooked = hour_wasted = hour_stockouts = 0

        # Calculate current 15-min slot index (0-671)
        slot_idx = ((weekday_int * 96) + (hour * 4) + (sim_now.minute // 15)) % 672

        # Check if store is open
        is_open = True
        if store_hours == "5am-11pm" and (hour < 5 or hour >= 23):
            is_open = False

        if not is_open:
            await asyncio.sleep(TICK_INTERVAL)
            continue

        # --- 1. SALES GENERATION (Poisson) ---
        random_offset = random.choices(RANDOMNESS[level]["values"],
                                       weights=RANDOMNESS[level]["weights"])[0]
        hourly_lambda = (RUSH_CURVE[hour] * WEEKDAY_MULTIPLIER[weekday_int] *
                         (BASE_VOLUME[level] + random_offset))

        sim_seconds_per_tick = TICK_INTERVAL * TIME_SCALE
        tick_lambda = (hourly_lambda / 3600) * sim_seconds_per_tick

        num_customers = np.random.poisson(tick_lambda)

        if num_customers > 0:
            available_items = [
                item for item in menu["items"]
                if item["active"]
                and item["added"] <= sim_now.date()
                and hour in range(HOURS_AVAILABLE[item["time_of_day"]][0],
                                  HOURS_AVAILABLE[item["time_of_day"]][1])
            ]

            if available_items:
                popularity_weights = [i["popularity"] for i in available_items]
                for _ in range(num_customers):
                    item = random.choices(available_items,
                                          weights=popularity_weights)[0]

                    qty_to_sell = random.choices([1, 2, 3],
                                                 weights=[0.7, 0.2, 0.1])[0]
                    actual_sold = state.consume(item["id"], qty_to_sell)

                    if actual_sold > 0:
                        price = item["sale_price"] if weekday_int in \
                            item.get("sale_days", []) else item["price"]
                        asyncio.create_task(fire_sale(client, store_id,
                                    item["id"], actual_sold, price, sim_now))
                        print(f"[{store_id}] SALE: {item['id']} x{actual_sold} "
                              f"@ ${price:.2f} | {sim_now.strftime('%H:%M')}")
                        hour_sales += actual_sold
                    else:
                        asyncio.create_task(fire_stockout(client, store_id, item["id"],
                                            qty_to_sell, sim_now))
                        hour_stockouts += qty_to_sell

        # --- 2. PRODUCTION LOGIC (Sliding Window Replenishment) ---
        if slot_idx != last_slot_idx:
            last_slot_idx = slot_idx
            for item in menu["items"]:
                if (not item["active"] and item["added"] <= sim_now.date()
                    and hour not in range(
                        HOURS_AVAILABLE[item["time_of_day"]][0],
                        HOURS_AVAILABLE[item["time_of_day"]][1])
                        ):
                    continue

                look_ahead = int(item["hold_time"] * 4)
                demand = sum(production_targets.get(
                    (store_id, (slot_idx + i) % 672, item["id"]), 0)
                        for i in range(look_ahead))

                committed = (state.get_total_quantity(item["id"]) +
                    state.get_in_progress_quantity(item["id"]))

                gap = demand - committed

                batch_floor = item["batch"] * RUSH_CURVE[hour]
                if gap > 1:
                    cook_qty = (int(np.ceil(max(batch_floor, gap)))
                                if gap >= item["batch"] else int(np.ceil(gap)))
                else:
                    cook_qty = 0

                if cook_qty > 0:
                    ready_at = sim_now + timedelta(minutes=item["cook_time"])
                    expires = ready_at + timedelta(hours=item["hold_time"])
                    state.start_cooking(item["id"], cook_qty, ready_at, expires)
                    print(f"[{store_id}] COOK ORDER: {item['id']} x{cook_qty} | "
                          f"ready {ready_at.strftime('%H:%M')} | "
                          f"expires {expires.strftime('%H:%M')}")

                    hour_cooked += cook_qty

        # --- 3. WASTE LOGIC ---
        for item_id, batches in state.inventory.items():
            expired_batches = [b for b in batches if b["expires"] <= sim_now]
            state.inventory[item_id] = \
                [b for b in batches if b["expires"] > sim_now]

            for b in expired_batches:
                asyncio.create_task(fire_waste(
                    client, store_id, item_id, b["quantity"], sim_now))
                hour_wasted += b["quantity"]

        await asyncio.sleep(TICK_INTERVAL)


async def main():
    clock = SimClock(START_TIME, TIME_SCALE)
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=100)) as client:
        # Initial wait to let the targets load
        targets_task = asyncio.create_task(refresh_targets_task())

        print("[SIMULATOR] Waiting for production targets to load...")
        while not production_targets:
            await asyncio.sleep(1)

        tasks = [targets_task]

        # One simulator task per store
        for store in stores["stores"]:
            tasks.append(asyncio.create_task(simulate_store(store, clock, client)))

        print(f"--- SIMULATION STARTED (Scale: {TIME_SCALE}x) ---")
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSimulation stopped by user.")