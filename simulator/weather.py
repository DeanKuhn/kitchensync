"""Deterministic synthetic weather and its ground-truth demand effect.

Used only to generate training data (historical_generator.py /
fast_historical_generator.py) and the "actual" demand in the nightly A/B
simulation (scripts/run_daily_simulation.py). The ML model only ever sees the
raw temp_f/precip values returned by get_weather() as features -- the
multiplier in weather_demand_multiplier() is ground truth used to generate
data and must never be fed to the model directly, or it would be learning the
answer instead of the signal.

get_weather() is deterministic per (region, date): every caller (generators,
the dbt weather seed, the A/B script) must independently compute the exact
same weather for a given region+date without a shared runtime table. Seeding
random.Random() with a string is stable across processes -- CPython hashes
the string via sha512 internally, unlike the builtin hash() function, whose
PYTHONHASHSEED randomization would make this vary run to run.
"""

import random
from datetime import date

MIN_TEMP_F = 10.0
MAX_TEMP_F = 100.0
PRECIP_PROBABILITY = 0.22

HOT_THRESHOLD_F = 80.0
COLD_THRESHOLD_F = 40.0

PRECIP_VOLUME_FACTOR = 0.80

CATEGORY_TEMP_EFFECTS = {
    "chicken": (1.5, 1.0),
    "roller_grill": (1.5, 0.7),
    "sandwich": (0.75, 1.4),
    "side": (0.75, 1.4),
}


def get_weather(region: str, day: date) -> dict:
    """Deterministic synthetic weather for a (region, date) pair."""
    rng = random.Random(f"{region}|{day.isoformat()}")
    temp_f = rng.uniform(MIN_TEMP_F, MAX_TEMP_F)
    precip = rng.random() < PRECIP_PROBABILITY
    return {"temp_f": temp_f, "precip": precip}


def weather_demand_multiplier(
    weather: dict, category: str = None # type:ignore
) -> float:
    """Ground-truth demand multiplier for the given weather (+ category)."""
    factor = PRECIP_VOLUME_FACTOR if weather["precip"] else 1.0

    if category is None:
        return factor

    hot_mult, cold_mult = CATEGORY_TEMP_EFFECTS.get(category, (1.0, 1.0))
    temp_f = weather["temp_f"]

    if temp_f > HOT_THRESHOLD_F:
        factor *= hot_mult
    elif temp_f < COLD_THRESHOLD_F:
        factor *= cold_mult

    return factor
