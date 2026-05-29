# Training pipeline (baseline + LightGBM)

import os
import joblib
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
import lightgbm as lgb # type:ignore

from ml.features import load_features
import ml.features as features


def train_models():

    # Load the df from the features.py file
    df = load_features()

    FEATURE_COLS = features.FEATURE_COLS


    # Encode store_id and item_id
    store_encoder = LabelEncoder()
    item_encoder = LabelEncoder()

    df['store_id'] = store_encoder.fit_transform(df['store_id'])
    df['item_id'] = item_encoder.fit_transform(df['item_id'])


    # Chronological split, sort by date, then split 80/20
    df_sorted = df.sort_values('sale_date').reset_index(drop=True)
    split_idx = int(len(df_sorted) * 0.8)

    # Define features and target
    X = df_sorted[FEATURE_COLS]
    y = df_sorted['slot_quantity']

    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]


    # # Train the baseline model (RandomForest)
    # print("Training baseline model...")
    # baseline = RandomForestRegressor(n_estimators=100, random_state=42)
    # baseline.fit(X_train, y_train)

    # baseline_preds = baseline.predict(X_test)
    # baseline_mae = mean_absolute_error(y_test, baseline_preds)
    # baseline_rmse = root_mean_squared_error(y_test, baseline_preds)

    # print(f"Baseline MAE: {baseline_mae:.2f}")
    # print(f"Baseline RMSE: {baseline_rmse:.2f}")


    # Train the LightGBM model
    print("Training LightGBM model...")
    lgbm = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, random_state=42)
    lgbm.fit(X_train, y_train)

    lgbm_preds = lgbm.predict(X_test)
    lgbm_mae = mean_absolute_error(y_test, lgbm_preds)
    lgbm_rmse = root_mean_squared_error(y_test, lgbm_preds)

    print(f"LightGBM MAE:  {lgbm_mae:.2f}")
    print(f"LightGBM RMSE: {lgbm_rmse:.2f}")


    # Save models and encoders
    os.makedirs("ml/models", exist_ok=True)

    # joblib.dump(baseline, "ml/models/baseline.joblib")
    joblib.dump(lgbm, "ml/models/lgbm.joblib")
    joblib.dump(store_encoder, "ml/models/store_encoder.joblib")
    joblib.dump(item_encoder, "ml/models/item_encoder.joblib")

    print("Models and encoders saved to ml/models/")


    # Comparison
    # mae_improvement = (baseline_mae - lgbm_mae) / baseline_mae * 100
    # rmse_improvement = (baseline_rmse - lgbm_rmse) / baseline_rmse * 100
    # print(f"\nLightGBM vs Baseline: MAE improved {mae_improvement:.1f}%, "\
    #     f"RMSE improved {rmse_improvement:.1f}%")


if __name__ == "__main__":
    train_models()