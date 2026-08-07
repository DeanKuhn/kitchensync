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

Thresholds/factors retuned 2026-08 (decision #23) to make the weather signal
dominant rather than marginal: the original neutral band (40-80F) covered
~56% of days with zero temp effect, and the multipliers were small enough
that unrelated day-to-day volume noise (RANDOMNESS in pos_simulator.py /
fast_historical_generator.py) swamped them. The band is now 15F wide (~83%
of days get a temp effect) and every multiplier roughly doubled in strength.
"""

import random
from datetime import date

MIN_TEMP_F = 10.0
MAX_TEMP_F = 100.0
PRECIP_PROBABILITY = 0.35

HOT_THRESHOLD_F = 70.0
COLD_THRESHOLD_F = 55.0

PRECIP_VOLUME_FACTOR = 0.70

CATEGORY_TEMP_EFFECTS = {
    "chicken": (2.2, 1.0),
    "roller_grill": (2.2, 0.4),
    "sandwich": (0.45, 1.9),
    "side": (0.45, 1.9),
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
