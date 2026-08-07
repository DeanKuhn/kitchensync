# Reproducible replacement for the untracked, ad-hoc "5-day sample" weather
# comparison referenced in CLAUDE.md decision #22/#23. Buckets many
# independent store-days by that store-region's weather on the simulated
# date (extreme_heat / extreme_cold / precip / neutral, mirroring
# simulator/weather.py's weather_demand_multiplier() thresholds) and
# compares ML vs baseline service level / waste % within each bucket.
#
# Unlike run_daily_simulation.py (which simulates only "today" for the
# nightly cron), this script simulates a range of synthetic dates purely to
# get weather variety -- it never touches Neon's live sales/waste/stockout
# tables and doesn't feed data/ab_results_v2.json.

import hashlib
import json
import random
from datetime import datetime, timedelta

import numpy as np

from scripts.run_daily_simulation import (
    stores,
    load_ml_predictions,
    load_baseline_predictions,
    simulate_store_day,
)
from simulator.weather import get_weather, HOT_THRESHOLD_F, COLD_THRESHOLD_F

NUM_DAYS = 60
START_DATE = datetime(2026, 9, 1)
OUTPUT_PATH = "data/weather_impact_results.json"


def stable_seed(s: str) -> int:
    # Avoid builtin hash() -- PYTHONHASHSEED-randomized for strings, would
    # make np.random.seed() vary run to run (same reasoning as weather.py).
    return int(hashlib.sha256(s.encode()).hexdigest(), 16) % (2**32)


def classify_weather(weather: dict) -> str:
    """Buckets are mutually exclusive for reporting simplicity: precip takes
    priority (it affects every category), then temp extremes, else neutral.
    The ground-truth multiplier itself composes precip and temp effects
    together -- see weather_demand_multiplier() -- this bucketing is only for
    grouping the analysis output, not a re-derivation of the multiplier.
    """
    if weather["precip"]:
        return "precip"
    if weather["temp_f"] > HOT_THRESHOLD_F:
        return "extreme_heat"
    if weather["temp_f"] < COLD_THRESHOLD_F:
        return "extreme_cold"
    return "neutral"


def run_store_day(store, predictions, day_of_week, seed_date, mode):
    # Seed is intentionally independent of `mode` -- ml and baseline must draw
    # the same Poisson/random-choice sequence for a given store-day, or a
    # difference in outcomes could just be sampling noise rather than a real
    # production-decision difference.
    seed_str = f"{seed_date.isoformat()}|{store['id']}"
    random.seed(seed_str)
    np.random.seed(stable_seed(seed_str))
    return simulate_store_day(store, predictions, day_of_week, seed_date, mode)


def main():
    baseline_predictions = load_baseline_predictions()

    buckets = {
        "extreme_heat": {"ml": _empty_metrics(), "baseline": _empty_metrics(), "n": 0},
        "extreme_cold": {"ml": _empty_metrics(), "baseline": _empty_metrics(), "n": 0},
        "precip": {"ml": _empty_metrics(), "baseline": _empty_metrics(), "n": 0},
        "neutral": {"ml": _empty_metrics(), "baseline": _empty_metrics(), "n": 0},
    }

    for day_idx in range(NUM_DAYS):
        seed_date = START_DATE + timedelta(days=day_idx)
        day_of_week = seed_date.weekday()

        print(f"[WEATHER IMPACT] Simulating {seed_date.date()}...")
        ml_predictions = load_ml_predictions(seed_date)

        for store in stores["stores"]:
            weather = get_weather(store["region"], seed_date.date())
            bucket = classify_weather(weather)

            ml_metrics = run_store_day(store, ml_predictions, day_of_week, seed_date, "ml")
            base_metrics = run_store_day(store, baseline_predictions, day_of_week, seed_date, "baseline")

            _accumulate(buckets[bucket]["ml"], ml_metrics)
            _accumulate(buckets[bucket]["baseline"], base_metrics)
            buckets[bucket]["n"] += 1

    results = {}
    print("\n--- WEATHER IMPACT SUMMARY ---")
    print(f"{'bucket':<14}{'n':>6}{'ml_svc%':>10}{'base_svc%':>11}{'gap_pp':>9}"
          f"{'ml_waste%':>11}{'base_waste%':>13}")
    for bucket_name, bucket_data in buckets.items():
        n = bucket_data["n"]
        if n == 0:
            continue
        ml_svc = _service_level(bucket_data["ml"])
        base_svc = _service_level(bucket_data["baseline"])
        ml_waste = _waste_pct(bucket_data["ml"])
        base_waste = _waste_pct(bucket_data["baseline"])
        gap = ml_svc - base_svc

        print(f"{bucket_name:<14}{n:>6}{ml_svc:>10.2f}{base_svc:>11.2f}{gap:>9.2f}"
              f"{ml_waste:>11.2f}{base_waste:>13.2f}")

        results[bucket_name] = {
            "store_days": n,
            "ml_service_level": round(ml_svc, 2),
            "baseline_service_level": round(base_svc, 2),
            "service_level_gap_pp": round(gap, 2),
            "ml_waste_pct": round(ml_waste, 2),
            "baseline_waste_pct": round(base_waste, 2),
        }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote bucketed results to {OUTPUT_PATH}")


def _empty_metrics():
    return {"units_sold": 0, "stockouts": 0, "units_wasted": 0,
             "waste_cost": 0.0, "sales_revenue": 0.0}


def _accumulate(totals, metrics):
    for key in totals:
        totals[key] += metrics[key]


def _service_level(totals):
    denom = totals["units_sold"] + totals["stockouts"]
    return (totals["units_sold"] / denom * 100) if denom else 0.0


def _waste_pct(totals):
    return (totals["waste_cost"] / totals["sales_revenue"] * 100) \
        if totals["sales_revenue"] else 0.0


if __name__ == "__main__":
    main()
