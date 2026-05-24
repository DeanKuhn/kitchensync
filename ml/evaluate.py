# MAE, RMSE, urgency precision/recall


import os
import joblib
import pandas as pd
from dotenv import load_dotenv # type:ignore
from sklearn.metrics import \
    mean_absolute_error, root_mean_squared_error, classification_report

from ml.features import load_features
load_dotenv()


def load_test_data(se, ie):

    # Load features of dataframe
    df = load_features()


    # Use joblib encoders to transform columns
    df['store_id'] = se.transform(df['store_id'])
    df['item_id'] = ie.transform(df['item_id'])


    # Chronological split, same as training
    df_sorted = df.sort_values('sale_date').reset_index(drop=True)
    split_idx = int(len(df_sorted) * 0.8)


    # Define features and target
    X = df_sorted.drop(columns=['hourly_quantity', 'sale_date'])
    y = df_sorted['hourly_quantity']

    X_test = X.iloc[split_idx:]
    y_test = y.iloc[split_idx:]
    test_avg_hour_quantity = X_test['avg_hourly_quantity']


    return X_test, y_test, test_avg_hour_quantity


def evaluate_regression(model, X_test, y_test, name):

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    rmse = root_mean_squared_error(y_test, preds)
    print(f"{name} MAE: {mae:.2f}")
    print(f"{name} RMSE: {rmse:.2f}")
    return mae, rmse, preds


def evaluate_urgency(y_test, preds, avg_hourly_quantity, name):

    # Create two boolean arrays for urgency calculation
    threshold = avg_hourly_quantity * float(os.getenv("URGENCY_THRESHOLD"))
    actual_urgent = y_test > threshold
    predicted_urgent = preds > threshold

    print(f"\n--- Urgency Report: {name} ---")
    print(classification_report(actual_urgent, predicted_urgent,
                                target_names=["NORMAL", "URGENT"]))


if __name__ == "__main__":

    # Load both models for comparison
    baseline = joblib.load("ml/models/baseline.joblib")
    lgbm = joblib.load("ml/models/lgbm.joblib")

    # Load specific encoders
    store_encoder = joblib.load("ml/models/store_encoder.joblib")
    item_encoder = joblib.load("ml/models/item_encoder.joblib")

    # Get X_test, y_test, and the avg_hourly_quantity for urgency testing
    X_test, y_test, avg_hourly_quantity = \
        load_test_data(store_encoder, item_encoder)

    # Get both the baseline and lgbm stats
    baseline_mae, baseline_rmse, baseline_preds = \
        evaluate_regression(baseline, X_test, y_test, "Baseline")
    lgbm_mae, lgbm_rmse, lgbm_preds = \
        evaluate_regression(lgbm, X_test, y_test, "LGBM")

    # Comparison, same as in training.py
    mae_improvement = (baseline_mae - lgbm_mae) / baseline_mae * 100
    rmse_improvement = (baseline_rmse - lgbm_rmse) / baseline_rmse * 100
    print(f"\nLightGBM vs Baseline: MAE improved {mae_improvement:.1f}%, "\
        f"RMSE improved {rmse_improvement:.1f}%")

    # Also, see how well each model did determining urgency
    evaluate_urgency(y_test, baseline_preds, avg_hourly_quantity, "Baseline")
    evaluate_urgency(y_test, lgbm_preds, avg_hourly_quantity, "LGBM")