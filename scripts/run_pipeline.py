# This runs the model retraining pipeline that would theoretically get ran
# nightly for a real-world model

# 1. Extract rows in Neon database to Snowflake's RAW.SALES_EVENTS
# 2. Re-run all dbt processes
# 3. Retrain model
# 4. Create new predictions based on the new model's training

# These predictions are then used in the next day's pos_simulator, which
# simulates sales, waste, and batches made by the kitchen


import subprocess
import sys

if __name__ == "__main__":
    steps = [
        ["uv", "run", "python", "-m", "scripts.extract_to_snowflake"],
        ["uv", "run", "dbt", "run", "--project-dir", "dbt"],
        ["uv", "run", "python", "-m", "ml.train"],
        ["uv", "run", "python", "-m", "ml.predict"],
    ]

    for step in steps:
        print(f"\n--- Running: {' '.join(step)} ---")
        result = subprocess.run(step)
        if result.returncode != 0:
            print(f"Step failed: {' '.join(step)}")
            sys.exit(1)

    print("\nPipeline complete.")