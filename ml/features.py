from dotenv import load_dotenv # type:ignore


load_dotenv()


FEATURE_COLS = [
    'store_id',
    'item_id',
    'sale_hour',
    'sale_minute',
    'slot_index',
    'day_of_week',
    'is_weekend',
    'avg_slot_quantity',
    'sample_size',
    'temp_f',
    'precip'
]


def load_features():
    """Recomputes scripts/build_training_features.py's Neon-native port of
    mart_ml_training_features in-memory each call.
    """
    from scripts.build_training_features import build_features

    df = build_features()

    # Adds new column: 1 if Saturday or Sunday, 0 else (0=Monday..6=Sunday)
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)

    # Postgres boolean -> pandas bool; cast to int like is_weekend for a
    # model-friendly numeric dtype
    df['precip'] = df['precip'].astype(int)

    return df