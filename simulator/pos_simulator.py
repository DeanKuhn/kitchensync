import asyncio
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

# Ensure date parsing for cold-start logic
for item in menu["items"]:
    if isinstance(item["added"], str):
        item["added"] = datetime.strptime(item["added"], "%Y-%m-%d").date()


# --- CONFIGURATION ---
TIME_SCALE = 120  # 1 real second = 2 simulation minutes
API_BASE_URL = "http://localhost:8000"
TICK_INTERVAL = 1  # Seconds between loop iterations
START_TIME = datetime(2026, 2, 12, 0, 0, 0)

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

# Global state for prescriptive targets: (store_id, slot_index, item_id) -> target_qty
production_targets = {}


# --- UTILITY CLASSES ---
class SimClock:
    def __init__(self, start_time, time_scale):
        self.start_time = start_time
        self.time_scale = time_scale
        # Record exactly when the simulation started in the real world
        self.real_start = asyncio.get_event_loop().time()

    def now(self):
        """Returns the current simulation datetime."""
        real_elapsed = asyncio.get_event_loop().time() - self.real_start
        sim_elapsed_seconds = real_elapsed * self.time_scale
        return self.start_time + timedelta(seconds=sim_elapsed_seconds)

class StoreState:
    def __init__(self, store_id):
        self.store_id = store_id
        # inventory format: { "ITEM_ID": [batch1, batch2, ...] }
        self.inventory = {}


    def add_batch(self, item_id, quantity, expires):

        # Adds freshly cooked food to the display.
        if item_id not in self.inventory:
            self.inventory[item_id] = []
        self.inventory[item_id].append({"quantity": quantity, "expires": expires})


    def consume(self, item_id, quantity):
        """Removes food when sold. Returns actual quantity sold."""
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

        # Returns total quantity available for an item across all batches.
        return sum(batch["quantity"] for batch in self.inventory.get(item_id, []))


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

    # Background task to load the 15-minute prescriptive targets from Snowflake.
    # Since this is a historical profile, we load it once at start and then refresh
    # only occasionally.

    engine = get_snowflake_engine()
    global production_targets

    while True:
        try:
            print("[SIMULATOR] Loading 15-min production targets from Snowflake...")
            query = text("""
                SELECT store_id, slot_index, item_id, target_inventory
                FROM MARTS.MART_PRODUCTION_TARGETS
            """)

            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, lambda: pd.read_sql(query, engine))

            new_targets = {}
            for _, row in df.iterrows():
                # Key: (store_id, slot_index, item_id)
                key = (row['STORE_ID'], int(row['SLOT_INDEX']), row['ITEM_ID'])
                new_targets[key] = float(row['TARGET_INVENTORY'])

            production_targets = new_targets
            print(f"[SIMULATOR] Loaded {len(production_targets)} prescriptive targets.")
        except Exception as e:
            print(f"[TARGETS ERROR] {e}")

        # Historical profiles are static; we only refresh every hour just in case
        await asyncio.sleep(3600)


# --- SIMULATION FUNCTION ---
async def simulate_store(config, clock, client):

    store_id = config["id"]
    level = int(config["level"])
    store_hours = config["hours"]

    state = StoreState(store_id)
    print(f"[{store_id}] Simulator started.")

    while True:
        sim_now = clock.now()
        hour = sim_now.hour
        weekday_int = sim_now.weekday()

        # Calculate current 15-min slot index (0-671)
        slot_idx = (weekday_int * 96) + (hour * 4) + (sim_now.minute // 15)

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
                    else:
                        await fire_stockout(client, store_id, item["id"],
                                            qty_to_sell, sim_now)

        # --- 2. PRODUCTION LOGIC (Sliding Window Replenishment) ---
        # Instead of fixed hourly jumps, we maintain the 'Target Inventory'
        # for the current 15-minute slot.
        for item in menu["items"]:
            if not item["active"]: continue

            target_qty = production_targets.get((store_id, slot_idx, item["id"]), 0)
            current_qty = state.get_total_quantity(item["id"])

            # If our current shelf stock is below the target needed for
            # the next hold_time window, cook the difference.
            if current_qty < target_qty:
                cook_qty = int(np.ceil(target_qty - current_qty))
                expiration = sim_now + timedelta(hours=item["hold_time"])
                state.add_batch(item["id"], cook_qty, expiration)

        # --- 3. WASTE LOGIC ---
        for item_id, batches in state.inventory.items():
            expired_batches = [b for b in batches if b["expires"] <= sim_now]
            state.inventory[item_id] = \
                [b for b in batches if b["expires"] > sim_now]

            for b in expired_batches:
                asyncio.create_task(fire_waste(
                    client, store_id, item_id, b["quantity"], sim_now))

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
