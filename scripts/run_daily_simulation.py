# imports
import pandas as pd
from sqlalchemy import text # type:ignore
import yaml # type:ignore
import random
from datetime import datetime, timedelta
import numpy as np
import json


# shared constraints pulled from pos_simulator
from simulator.pos_simulator import (
    RUSH_CURVE,
    BASE_VOLUME,
    RANDOMNESS,
    HOURS_AVAILABLE,
    WEEKDAY_MULTIPLIER,
)

from simulator.pos_simulator import StoreState
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


def load_ml_predictions():

    # Load ML model predictions from Snowflake
    engine = get_snowflake_engine()

    try:
        print("[SIMULATOR] Loading 15-min ML production targets from Snowflake...")
        query = text("""
            SELECT store_id, slot_index, item_id, predicted_units
            FROM MARTS.PREDICTIONS
        """)

        df = pd.read_sql(query, engine)
        df.columns = df.columns.str.lower()

        # Return dict keyed by (store_id, slot_index, item_id)
        ml_production_targets = {}
        for _, row in df.iterrows():
            key = (
                row['store_id'],
                int(row['slot_index']),
                row['item_id']
            )
            ml_production_targets[key] = float(row['predicted_units'])

        print(f"[SIMULATOR] Loaded {len(ml_production_targets)} "
               "prescriptive targets for ML model.")
        return ml_production_targets

    except Exception as e:
        print(f"[TARGETS ERROR FOR ML] {e}")


def load_baseline_predictions():

    # Load baseline model predictions from Snowflake
    engine = get_snowflake_engine()

    try:
        print("[SIMULATOR] Loading hourly baseline production targets from Snowflake...")
        query = text("""
            SELECT store_id, item_id, day_of_week, sale_hour,
                SUM(avg_slot_quantity) as hourly_quantity
            FROM INTERMEDIATE.INT_SALES__TIME_OF_DAY_PROFILE
            GROUP BY store_id, item_id, day_of_week, sale_hour
        """)

        df = pd.read_sql(query, engine)
        df.columns = df.columns.str.lower()

        # Return dict keyed by (store_id, day_of_week, sale_hour, item_id)
        base_production_targets = {}
        for _, row in df.iterrows():
            key = (
                row['store_id'],
                int(row['day_of_week']),
                int(row['sale_hour']),
                row['item_id']
            )
            base_production_targets[key] = float(row['hourly_quantity'])

        print(f"[SIMULATOR] Loaded {len(base_production_targets)} "
               "prescriptive targets for baseline model.")
        return base_production_targets

    except Exception as e:
        print(f"[TARGETS ERROR FOR BASELINE] {e}")


def simulate_store_day(store_config, predictions, day_of_week, seed_date, mode):

    store_id = store_config["id"]
    level = int(store_config["level"])
    state = StoreState(store_id)
    store_hours = store_config["hours"]

    print(f"[{mode.upper()}] Simulating {store_id}...")

    metrics = {
        "units_wasted": 0,
        "waste_cost": 0.0,
        "stockouts": 0,
        "units_sold": 0,
        "sales_revenue": 0.0
    }
    waste_by_item = {}
    cooked_by_item = {}

    menu_lookup = {item["id"]: item for item in menu["items"]}

    # Start of day lineup
    if store_hours != "5am-11pm":
        seed_datetime = datetime(seed_date.year, seed_date.month, seed_date.day)

        for item in menu["items"]:
            if not item["active"]: continue
            if item["added"] > seed_date.date(): continue
            if 0 not in range(
                    HOURS_AVAILABLE[item["time_of_day"]][0],
                    HOURS_AVAILABLE[item["time_of_day"]][1]
                    ):
                continue

            if mode == "ml":
                global_slot = day_of_week * 96
                look_ahead = int(item["hold_time"] * 4)
                demand = int(round(sum(predictions.get(
                    (store_id, (global_slot + i) % 672, item["id"]), 0)
                    for i in range(look_ahead))))

            else:
                look_ahead = int(item["hold_time"])
                demand = int(round(sum(predictions.get(
                    (store_id, day_of_week, i % 24, item["id"]), 0)
                    for i in range(look_ahead))))

            if demand > 0:
                expires = seed_datetime + timedelta(hours=item["hold_time"])
                state.inventory[item["id"]] = [{"quantity": demand,
                                                "expires": expires}]

    for slot_idx in range(96):

        hour = slot_idx // 4
        if store_hours == "5am-11pm" and (hour < 5 or hour >= 23):
            continue

        global_slot = (day_of_week * 96) + slot_idx

        sim_now = (datetime(seed_date.year, seed_date.month, seed_date.day) +
                timedelta(minutes=slot_idx * 15))

        state.promote_ready_batches(sim_now, store_id)

        # --- PRODUCTION LOGIC ---
        fires = (mode == "ml") or (mode == "baseline" and slot_idx % 4 == 0)

        if fires:
            for item in menu["items"]:
                if not item["active"]: continue
                if item["added"] > seed_date.date(): continue
                if hour not in range(
                        HOURS_AVAILABLE[item["time_of_day"]][0],
                        HOURS_AVAILABLE[item["time_of_day"]][1]
                        ):
                    continue

                if mode == "ml":
                    look_ahead = int(item["hold_time"] * 4)
                    demand = sum(predictions.get(
                        (store_id, (global_slot + i) % 672, item["id"]), 0)
                        for i in range(look_ahead))

                else:
                    look_ahead = int(item["hold_time"])
                    demand = sum(predictions.get(
                        (store_id, (day_of_week + (hour + i) // 24) % 7,
                         (hour + i) % 24, item["id"]), 0)
                        for i in range(look_ahead))

                committed = (state.get_total_quantity(item["id"]) +
                            state.get_in_progress_quantity(item["id"]))
                gap = demand - committed

                cook_qty = int(np.ceil(max(
                    item["batch"] * RUSH_CURVE[hour], gap))
                    ) if gap > 1 else 0

                if cook_qty > 0:
                    ready_at = sim_now + timedelta(minutes=item["cook_time"])
                    expires = ready_at + timedelta(hours=item["hold_time"])
                    state.start_cooking(item["id"], cook_qty, ready_at, expires)
                    cooked_by_item[item["id"]] = cooked_by_item.get(item["id"], 0) + cook_qty

        # --- POISSON/SALES LOGIC ---
        random_offset = random.choices(RANDOMNESS[level]["values"],
                            weights=RANDOMNESS[level]["weights"])[0]
        hourly_lambda = (RUSH_CURVE[hour] * WEEKDAY_MULTIPLIER[day_of_week] *
                            (BASE_VOLUME[level] + random_offset))

        tick_lambda = (hourly_lambda / 4) # 15 minute slots

        num_customers = np.random.poisson(tick_lambda)

        if num_customers > 0:
            available_items = [
                item for item in menu["items"]
                if item["active"]
                and item["added"] <= seed_date.date()
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
                        price = item["sale_price"] if day_of_week in \
                            item.get("sale_days", []) else item["price"]
                        metrics["units_sold"] += actual_sold
                        metrics["sales_revenue"] += actual_sold * price
                    else:
                        metrics["stockouts"] += qty_to_sell

        # --- WASTE LOGIC ---
        for item_id, batches in state.inventory.items():
            expired_batches = [b for b in batches if b["expires"] <= sim_now]
            state.inventory[item_id] = \
                [b for b in batches if b["expires"] > sim_now]

            for b in expired_batches:
                metrics["units_wasted"] += b["quantity"]
                metrics["waste_cost"] += b["quantity"] * menu_lookup[item_id]["cost"]
                waste_by_item[item_id] = waste_by_item.get(item_id, 0) + b["quantity"]

    # --- DEBUG BREAKDOWN ---
    waste_by_tod = {}
    cooked_by_tod = {}
    for item_id, qty in waste_by_item.items():
        tod = menu_lookup[item_id]["time_of_day"]
        waste_by_tod[tod] = waste_by_tod.get(tod, 0) + qty
    for item_id, qty in cooked_by_item.items():
        tod = menu_lookup[item_id]["time_of_day"]
        cooked_by_tod[tod] = cooked_by_tod.get(tod, 0) + qty

    print(f"\n[DEBUG][{mode.upper()}][{store_id}] sold={metrics['units_sold']} "
          f"wasted={metrics['units_wasted']} cooked={sum(cooked_by_item.values())}")
    print(f"  Waste by time_of_day: {waste_by_tod}")
    print(f"  Cooked by time_of_day: {cooked_by_tod}")
    top_wasted = sorted(waste_by_item.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"  Top 5 wasted items: {top_wasted}")

    return metrics


def simulate_day(predictions, seed_date, mode):

    random.seed(seed_date.isoformat())
    np.random.seed(hash(seed_date.isoformat()) % (2**32))

    day_of_week = seed_date.weekday()

    totals = {"units_sold": 0,
              "stockouts": 0,
              "units_wasted": 0,
              "waste_cost": 0.0,
              "sales_revenue": 0.0}

    for store in stores["stores"]:
        store_metrics = simulate_store_day(
            store, predictions, day_of_week, seed_date, mode)
        for key in totals:
            totals[key] += store_metrics[key]

    return totals


def load_ab_results(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"cumulative": {}, "daily": []}


def save_ab_results(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def compute_cumulative(daily):
    days_run = len(daily)

    ml_waste_pct = (sum(day["ml"]["waste_cost"] /
                    day["ml"]["sales_revenue"]
                    * 100 for day in daily) / len(daily))
    base_waste_pct = (sum(day["baseline"]["waste_cost"] /
                      day["baseline"]["sales_revenue"]
                      * 100 for day in daily) / len(daily))

    ml_service_level = (sum(day["ml"]["units_sold"] /
                        (day["ml"]["units_sold"] + day["ml"]["stockouts"])
                        * 100 for day in daily) / len(daily))

    base_service_level = (sum(day["baseline"]["units_sold"] /
                        (day["baseline"]["units_sold"] + day["baseline"]["stockouts"])
                        * 100 for day in daily) / len(daily))

    return {
        "days_run": days_run,
        "ml_avg_waste_pct": round(ml_waste_pct, 2),
        "baseline_avg_waste_pct": round(base_waste_pct, 2),
        "ml_avg_service_level": round(ml_service_level, 2),
        "base_avg_service_level": round(base_service_level, 2)
    }


def main():

    # Load prediction dictionaries
    ml_predictions = load_ml_predictions()
    baseline_predictions = load_baseline_predictions()

    # Set seed_date
    seed_date = datetime.now()

    # Call simulate_day twice, storing results
    ml_totals = simulate_day(ml_predictions, seed_date, mode="ml")
    baseline_totals = simulate_day(baseline_predictions, seed_date, mode="baseline")

    # Load existing results
    data = load_ab_results("data/ab_results.json")

    # Build today's entry dict and append to data["daily"]
    entry_dict = {
        "date": seed_date.strftime("%Y-%m-%d"),
        "ml": ml_totals,
        "baseline": baseline_totals
    }

    data["daily"].append(entry_dict)

    # Recompute cumulative
    data["cumulative"] = compute_cumulative(data["daily"])

    # Save
    save_ab_results("data/ab_results.json", data)


if __name__ == "__main__":
    main()