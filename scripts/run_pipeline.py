# Daily pipeline: baseline profile → A/B simulation → ab_results.json
# Run manually or via kitchensync-pipeline.timer (systemd).
# Snowflake retired entirely (2026-08) — predictions and the baseline
# profile are read from and written to Neon exclusively. See CLAUDE.md's
# retrain playbook for the manual steps used to refresh public.predictions
# (python -m ml.train then python -m ml.predict, no Snowflake involved).


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

    run("PYTHONPATH=. uv run python scripts/build_baseline_profile.py",
        "Build baseline profile (Neon)")

    run("PYTHONPATH=. uv run python scripts/run_daily_simulation.py",
        "A/B simulation → data/ab_results_v2.json")

    run("git add data/ab_results_v2.json && (git diff --cached --quiet || git commit -m \"Daily A/B results $(date +%Y-%m-%d)\") && git pull --rebase origin master && git push",
        "Commit and push ab_results_v2.json")

    elapsed = (datetime.now() - start).seconds
    print(f"\n[PIPELINE] Complete in {elapsed}s.")


if __name__ == "__main__":
    main()