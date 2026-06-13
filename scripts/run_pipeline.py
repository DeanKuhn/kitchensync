# Daily pipeline: extract → dbt → predict → A/B simulation → ab_results.json
# Run manually or via kitchensync-pipeline.timer (systemd).


import subprocess
import sys
from datetime import datetime


def run(cmd, label):
    print(f"\n[PIPELINE] {label}...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"[PIPELINE ERROR] {label} failed (exit {result.returncode}). Aborting.")
        sys.exit(result.returncode)
    print(f"[PIPELINE] {label} done.")


def main():
    start = datetime.now()
    print(f"[PIPELINE] Starting at {start.strftime('%Y-%m-%d %H:%M:%S')}")

    run("PYTHONPATH=. uv run python scripts/extract_to_snowflake.py",
        "Extract Neon → Snowflake RAW")

    run("uv run dbt run --project-dir dbt",
        "dbt: RAW → STAGING → INTERMEDIATE → MARTS")

    run("PYTHONPATH=. uv run python -m ml.predict",
        "Predict: refresh MARTS.PREDICTIONS")

    run("PYTHONPATH=. uv run python scripts/run_daily_simulation.py",
        "A/B simulation → data/ab_results.json")

    elapsed = (datetime.now() - start).seconds
    print(f"\n[PIPELINE] Complete in {elapsed}s.")


if __name__ == "__main__":
    main()