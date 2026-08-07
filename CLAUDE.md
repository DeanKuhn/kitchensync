# CLAUDE.md — KitchenSync Food Forecasting System

This file is the authoritative reference for Claude Code. Read it in full before taking any action in this project.

---

## Project Overview

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). The system ingests real-time simulated POS (point-of-sale) events, buffers them in memory and batch-writes to a Postgres-backed transactional database (Neon) every 5 minutes (decision #18), and feeds a LightGBM forecasting model that produces per-store, per-item production plans at 15-minute slot grain. A Streamlit dashboard surfaces results for kitchen staff, split into Kitchen and Chicken production queues. An A/B comparison pipeline runs nightly on AWS EC2, comparing the ML system against a naive hourly-average baseline; results are written to `data/ab_results_v2.json`, committed to GitHub, and consumed by a static Astro portfolio site. (`data/ab_results.json` is a frozen pre-retune archive, decision #17 — don't write to it.)

Snowflake is retired entirely (decision #12). Everything — training, inference, the dashboard, the A/B pipeline — reads/writes Neon exclusively. The dbt project remains in the repo as a portfolio-only artifact (see `dbt/README.md`) demonstrating a transformation-layer approach; nothing live depends on it.

This project exists to demonstrate: robust data pipeline engineering, scalable multi-store architecture, a modern analytics stack (dbt, portfolio-only), ML model accuracy with real-time adaptation, and automated cloud deployment on a cost-conscious footprint.

---

## Architecture Overview

```
[POS Simulator — EC2 systemd]
   buffers sales/waste/stockout in memory; every 5 min, opens one
   short-lived connection per store and bulk-inserts (decision #18)
                                                              │
                                                              ▼
                                                     [Neon (Postgres)]
                                                     Per-store schemas
                                              + shared public.predictions
                                              + shared public.baseline_profile
                                                              │
                                              [Nightly cron — 2am UTC]
                                          scripts/build_baseline_profile.py
                                    (ports dbt's time_of_day_profile logic to Neon SQL,
                                     rebuilds public.baseline_profile from raw sales_events)
                                                              │
                                          ┌───────────────────┴───────────────────┐
                                          ▼                                       ▼
                              [Streamlit Dashboard]                  [A/B Comparison — run_daily_simulation.py]
                     Split Kitchen / Chicken production queues        ML (public.predictions) vs Baseline
                     Current 15-min slot | 5-min auto-refresh          (public.baseline_profile), seeded by date
                          Missed Demand + Waste Summary                                    │
                     Reads public.predictions + live Neon stockout/waste                   ▼
                                                                                data/ab_results_v2.json
                                                                                             │
                                                                                git commit + push
                                                                                             │
                                                                                [Astro Portfolio Site]
                                                                           Daily ML vs Baseline metrics display


  ── Manual retrain path (Neon only, no Snowflake) ──

  scripts/build_training_features.py (in-memory) → ml.train → ml.predict
                                                                       │
                                                                       ▼
                                                          public.predictions (Neon)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| POS Simulation | Python (asyncio, Poisson arrivals, FIFO batch management); writes directly to Neon in 5-min batches, no ingest API (decision #18) |
| Transactional DB | Neon (cloud Postgres) — per-store schemas, plus shared `public.predictions` / `public.baseline_profile` / `public.cold_start_profile` / `public.traffic_ratio` / `public.weather_daily` |
| Analytics Warehouse | ~~Snowflake~~ retired; dbt kept as a portfolio-only artifact, not run against live data |
| ML — Baseline | Hourly average (in-memory, no model) |
| ML — Production | LightGBM |
| Dashboard | Streamlit + streamlit-autorefresh |
| A/B Comparison | Pure Python in-memory simulation |
| Portfolio Site | Static Astro site, fed by ab_results_v2.json |
| Cloud Hosting | AWS EC2 (systemd services + cron) |
| Config | YAML (menu, stores) |
| Package Management | uv |

---

## Repository Structure

```
kitchensync/
├── CLAUDE.md
├── README.md
├── Dockerfile                 # Shared simulator/dashboard image (production uses EC2 + systemd)
├── docker-compose.yml         # Full stack: simulator + dashboard
├── .env.example
├── pyproject.toml
│
├── config/
│   ├── menu.yaml              # Food items, categories, hold/cook times, active flags
│   └── stores.yaml            # 12 stores across 4 regions with traffic levels
│
├── data/
│   ├── ab_results.json            # Frozen pre-retune archive — never write to this (decision #17)
│   ├── ab_results_v2.json         # Live nightly A/B output — tracked in git, consumed by Astro site
│   ├── weather_impact_results.json # Output of scripts/weather_impact_analysis.py; manual/on-demand
│   ├── seeds/
│   └── exports/
│
├── simulator/
│   ├── pos_simulator.py       # Buffers sales/waste/stockout in memory, flushes to Neon every
│   │                             5 min via short-lived connections (decision #18) — no ingest API
│   ├── historical_generator.py       # Synthetic events via psycopg2 batch inserts (one call/day)
│   ├── fast_historical_generator.py  # Same logic, one execute_values call per store's whole
│   │                                    date range (page_size=10000) — prefer for bulk reseeding
│   └── weather.py             # Deterministic synthetic weather (get_weather, weather_demand_multiplier);
│                                 ground-truth-only, never fed to the model directly (decision #7)
│
├── api/
│   └── db/connection.py       # Neon connection pool (dashboard + one-off scripts only, minconn=0),
│                                 get_store_connection() with search_path
│
├── dbt/
│   ├── README.md              # Portfolio-only notice + model→Neon-script mapping
│   ├── models/                # staging → intermediate → marts (not run live)
│   └── ...
│
├── ml/
│   ├── features.py            # FEATURE_COLS; load_features() calls build_training_features.py in-memory
│   ├── train.py                # LightGBM training, saves lgbm.joblib + encoders
│   ├── predict.py              # Neon-native inference; generate_production_plan(weather_by_region=None)
│   │                              is the reusable entry point (see ML Model Design)
│   ├── evaluate.py
│   └── models/                 # lgbm.joblib, store_encoder.joblib, item_encoder.joblib
│
├── dashboard/
│   ├── app.py                  # Streamlit entry point, 5-min autorefresh
│   ├── components/             # production_plan.py (Kitchen/Chicken queues), store_selector.py
│   └── utils/data_fetch.py     # get_production_plan(), get_waste_summary() — all reads from Neon
│
├── scripts/
│   ├── init_db.py                    # One-time Neon schema + table creation
│   ├── run_pipeline.py               # Nightly cron: build_baseline_profile → A/B → git push
│   ├── build_baseline_profile.py     # Neon-native port of dbt's int_sales__time_of_day_profile
│   ├── build_cold_start_profile.py   # Neon-native port of dbt's mart_cold_start_profile
│   ├── build_traffic_ratio.py        # Neon-native port of dbt's mart_store_traffic_ratio
│   ├── build_training_features.py    # Neon-native port of mart_ml_training_features; NOT persisted
│   │                                    to Neon (joined result ~270MB vs. 512MB storage cap) —
│   │                                    ml/features.py calls build_features() in-memory instead
│   ├── generate_weather_seed.py      # Source of truth for synthetic weather: writes both
│   │                                    dbt/seeds/weather_daily.csv and Neon public.weather_daily
│   ├── run_daily_simulation.py       # A/B comparison — ML vs baseline, outputs data/ab_results_v2.json
│   ├── weather_impact_analysis.py    # Manual/on-demand — buckets simulated store-days by that day's
│   │                                    region weather, compares ML vs baseline per bucket, writes
│   │                                    data/weather_impact_results.json. Not part of the nightly cron.
│   └── delete_simulation_data.py     # Wipes simulation data from Neon
│
└── tests/
    ├── test_api.py
    ├── test_simulator.py
    └── test_ml_features.py
```

---

## Current State

- All 12 store schemas live in Neon (`sales_events`, `waste_log`, `stockout_events`)
- No ingest API — retired 2026-08 (decision #18); the simulator writes to Neon directly
- Historical generators (~70-day window, Poisson, sale-day and weather aware); `START_DATE` is a constant updated whenever the window is regenerated
- Live POS simulator: asyncio, SimClock, FIFO inventory, slot-boundary production logic, startup inventory seeding, 24h prediction reload from Neon, in-memory event buffering with a 5-min batched flush to Neon via short-lived connections (decision #18)
- LightGBM model trained on Neon-only features; predictions (12 stores × 45 active items × 672 slots, minus off-`time_of_day` slots) written to `public.predictions`
- Cold-start fallback via `public.cold_start_profile` (category-level avg by slot_index, threshold = 4 samples)
- Streamlit dashboard live at [kitchensync.streamlit.app](https://kitchensync.streamlit.app): split Kitchen/Chicken queues, current slot anchored to Neon's own clock (`get_sim_now()`, not wall-clock), missed demand, waste summary, 5-min autorefresh, session-state completion tracking
- A/B comparison (`run_daily_simulation.py`): in-memory, seeded by date, ML (`generate_production_plan()` with real per-date weather) vs. baseline (`public.baseline_profile`); writes `data/ab_results_v2.json` (`ab_results.json` is a frozen pre-retune archive, decision #17 — the Astro site still needs its data-source URL updated to the `_v2` filename, out of scope for this repo)
- `scripts/weather_impact_analysis.py`: manual/on-demand bucketed ML-vs-baseline comparison by weather condition, writes `data/weather_impact_results.json`
- AWS EC2: simulator as a systemd service (no API service to run anymore); single nightly cron line runs `run_pipeline.py` (`build_baseline_profile → A/B → git push`, guards against "nothing to commit")
- Synthetic weather (`simulator/weather.py`): gives the ML model a `(temp_f, precip)` axis the baseline's `(store, item, day_of_week, slot_index)` lookup structurally can't use; tuned deliberately strong for a portfolio-visible A/B gap (decision #17)

### Manual Retrain Playbook (Neon only, no Snowflake)

Retraining is manual and infrequent (decision #10):

1. `PYTHONPATH=. uv run python scripts/build_baseline_profile.py` — refresh `public.baseline_profile` from latest Neon data
2. `PYTHONPATH=. uv run python -m ml.train` — trains LightGBM on in-memory features (`build_training_features.py`), saves `ml/models/lgbm.joblib` + encoders
3. `PYTHONPATH=. uv run python -m ml.predict` — builds the full grid from `config/menu.yaml` + Neon profile tables, runs inference with a neutral weather placeholder, writes to `public.predictions`
4. Commit the refreshed `ml/models/*.joblib` files to git so EC2 can pull the new model without training on the t3.micro (which OOMs)

---

## Database Design (Neon / Postgres)

Each store gets its own schema: `store_012`, `store_027`, ... (12 total).

```sql
CREATE TABLE sales_events (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    price       NUMERIC(10, 2),
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE waste_log (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE stockout_events (
    id                 SERIAL PRIMARY KEY,
    item_id            TEXT,
    quantity_requested INT,
    created_at         TIMESTAMP DEFAULT now()
);
```

Shared `public` tables: `predictions`, `baseline_profile`, `cold_start_profile`, `traffic_ratio`, `weather_daily`.

**dbt** (portfolio-only, not run against live data) still documents staging → intermediate → marts models mirroring this design — see `dbt/README.md` for the model→Neon-script mapping and the slot-index formula (`(day_of_week * 96) + (sale_hour * 4) + FLOOR(sale_minute / 15)`, range 0–671, 0=Monday).

---

## ML Model Design

### Input Features
`sale_hour`, `sale_minute`, `slot_index`, `day_of_week`, `is_weekend` (derived), `avg_slot_quantity`, `sample_size` — all from `public.baseline_profile`. `temp_f`, `precip` from `public.weather_daily` (training) or a placeholder/actual value at inference (see below). `store_id`, `item_id` — encoded.

### Output
`predicted_units` (float, rounded to int at consumption) written to `public.predictions` (`store_id`, `item_id`, `predicted_units`, `slot_index`, `predicted_at`). Covers all 672 slots × 12 stores × 45 active items, minus rows outside an item's `time_of_day` window.

### Cold-Start
Items with fewer than 4 data points fall back to category-level averages from `public.cold_start_profile`, merged on `(category, slot_index)`.

### Inference
`ml/predict.py`'s `generate_production_plan(weather_by_region=None)` is the shared entry point. `weather_by_region=None` (the `__main__` path, used to refresh the dashboard's static weekly grid) applies a neutral weather placeholder, since that grid has no calendar date. `run_daily_simulation.py` instead passes real per-date-per-region weather as a "perfect forecast," giving the ML side a structural edge the baseline can't have (decision #7).

---

## Simulator Design

### Key Parameters
- `TIME_SCALE = 20` — 1 real second = 20 simulated seconds; `TICK_INTERVAL = 1` real second/tick
- `START_TIME`: `get_start_time()` queries `MAX(created_at)` across Neon per-store schemas and resumes from there; falls back to a hardcoded date if empty — keep this fallback in sync with `START_DATE` whenever the seed window is regenerated

### Production Logic
- Fires when `slot_idx != last_slot_idx and (is_rush or slot_idx % 4 == 0)`, `is_rush = RUSH_CURVE[hour] >= 0.6`
- Per item, skip the cook decision if `(not item["active"]) or (item["added"] > sim_now.date()) or (hour not in range(HOURS_AVAILABLE[...]))` — **must be OR, not AND** (an AND collapses to always-False for active items and cooks off-window items 24/7 — this exact bug shipped once, decision #8)
- `look_ahead = hold_time * 4` slots; `demand = sum(predictions over look_ahead)`; `gap = demand - (inventory + in_progress)`; `cook_qty = ceil(gap) if gap > 1 else 0` — **no minimum-batch floor** (removed deliberately, decision #6: a floor forces low-traffic stores to overproduce). This `ceil()`+`>1` rounding tax bites hardest on precip days when ML's correctly-low predictions sit near the threshold (decision #17) — a known, accepted tradeoff, not a bug.

### Startup Seeding
Inventory is pre-seeded with predicted units for the current slot, **rounded to a whole number** — `predicted_units` is an unrounded float and every other cook-quantity path rounds explicitly; this one must too or fractional quantities propagate through `consume()`/waste logging (decision #9).

### Background Tasks
- `refresh_targets_task()` reloads predictions from `public.predictions` at startup and every 24h.
- `flush_task()` (decision #18) — every `FLUSH_INTERVAL_SECONDS` (300s), drains each store's in-memory `pending_events` buffer and bulk-inserts sales/waste/stockout via `execute_values` over a short-lived connection opened and closed for that flush only. Buffers are swapped out (not cleared in place) before handing off to a thread executor, so `simulate_store()` can keep appending without racing the in-flight insert. On `KeyboardInterrupt`, `__main__` does one best-effort synchronous flush of whatever's still buffered; anything lost beyond that is bounded to at most one flush interval.

### Running
```bash
PYTHONPATH=. uv run streamlit run dashboard/app.py
PYTHONPATH=. uv run python -m simulator.pos_simulator
```

---

## Store & Menu Configuration

12 stores / 4 regions in `config/stores.yaml`: West Wisconsin (012, 027, 034), South Wisconsin (056, 061, 078), Minnesota (091, 103, 115), Iowa (128, 134, 147). Traffic levels 1–4; hours `24/7` or `5am-11pm`.

Menu in `config/menu.yaml`: `id`, `name`, `price`, `sale_price`, `sale_days`, `cost`, `time_of_day`, `category`, `hold_time`, `cook_time`, `popularity`, `active`, `added`.

- `time_of_day` windows: `all_day` [0,24], `breakfast` [4,12], `lunch` [10,22], `chicken` [9,22]
- `category`: `sandwich`, `side`, `roller_grill`, `chicken`, `appetizer` — drives cold-start grouping and waste display (Hot Foods = sandwich+side, Roller Grill = roller_grill, Chicken = chicken+appetizer)
- `sale_days`/`sale_price` apply a discount on matching weekdays (0=Monday); items without them always charge `price`
- `active: false` excludes an item from forecasting and simulation entirely
- `dbt/seeds/menu_items.csv` mirrors this file (portfolio-only; keep in sync if editing)

---

## Environment Variables

```
NEON_DATABASE_URL=postgresql://user:pass@host/dbname

URGENCY_THRESHOLD=2

# Optional, portfolio-only: only needed to run the dbt project against
# Snowflake directly. Nothing in the live pipeline reads these (decision #12).
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_DATABASE=...
SNOWFLAKE_WAREHOUSE=...
SNOWFLAKE_ROLE=...
SNOWFLAKE_PRIVATE_KEY_PATH=...
```

---

## Key Design Decisions

1. **Per-store Postgres schemas** — simpler `search_path`-based connection management; intentionally doesn't scale past ~50 stores.
2. **LightGBM over Prophet** — supports feature engineering; Prophet is a black box for interviews.
3. **15-min slot grain** — matches real KPS production planning cycles (672 slots/week).
4. **Config-driven menu** — items toggled without code changes; cold-start handles new items automatically.
5. **Slot-boundary production** — cook decisions fire once per 15-min boundary, not every tick; look-ahead = `hold_time * 4` slots.
6. **No minimum-batch floor** — a floor forces low-traffic stores to overproduce relative to genuinely thin demand; `cook_qty = ceil(gap) if gap > 1 else 0` has only rounding, no floor.
7. **Synthetic weather is ground-truth-only** — `weather_demand_multiplier()` generates data and drives the A/B ML side's "perfect forecast," but the model only ever sees raw `temp_f`/`precip` as features and must learn the interaction itself; gives ML a structural edge the baseline's date-less lookup can't have.
8. **Production time-of-day gate must be OR, not AND** — an earlier AND-chain collapsed to always-False for active items, causing off-window items (e.g. chicken) to get cooked 24/7 and chronically overproduce at low-traffic stores. Fixed; watch for this pattern if touching `pos_simulator.py`'s skip logic.
9. **Startup-seeded inventory must be rounded** — `predicted_units` is an unrounded float; seeding it directly let fractional quantities leak into `consume()`/waste logging for a batch's whole lifecycle. Always round cook/seed quantities explicitly.
10. **Retraining is manual** — nightly cron only rebuilds the baseline profile and runs the A/B comparison; the model itself is retrained via the playbook above and the resulting `.joblib` files are committed to git (EC2's t3.micro OOMs if it trains itself).
11. **A/B baseline never writes to Neon** — it's purely in-memory metrics, so baseline behavior can't corrupt the model's training signal.
12. **Snowflake retired entirely** — all Snowflake-touching code (extract, dbt-against-Snowflake, export-to-Neon) was deleted; Neon-native ports (`build_baseline_profile.py`, `build_cold_start_profile.py`, `build_traffic_ratio.py`, `build_training_features.py`) replace it. `build_training_features.py`'s output is deliberately **not persisted** to Neon (it hit ~270MB against a 512MB storage cap) — `ml/features.py` recomputes it in-memory each call instead. The dbt project was kept as a portfolio artifact only (see `dbt/README.md`), not deleted.
13. **Conditional-mean trap** — when computing average demand per slot, divide by *all* observed days for that slot (including zero-sale days), not just days with a sale, or low-traffic stores get inflated 3–4x. Applies to `build_baseline_profile.py` and any future profile-building script.
14. **"Latest per store" pattern** — any per-store "latest snapshot" query must partition/group by store, never a global `ORDER BY ... LIMIT 1`, which would silently collapse to one store.
15. **Honest A/B findings, not tuned away** — where ML underperforms the baseline on a subset (e.g. precip days, where the `ceil()`+`>1` rounding tax bites its correctly-low predictions harder, decision #17), that's reported as-is rather than engineered out, alongside where ML clearly wins (better service level, less waste elsewhere).
16. **`weather_impact_analysis.py` as a reproducible A/B methodology** — replaced an earlier untracked ad-hoc "5-day sample" comparison with a script that buckets many simulated store-days by that day's region weather and compares ML vs baseline within each bucket, writing `data/weather_impact_results.json`. Manual/on-demand, not part of the nightly cron.
17. **Weather signal retuned for a portfolio-visible gap (2026-08)** — the original weather tuning (decision #7) produced only a marginal ML-vs-baseline difference, because the baseline's `avg_slot_quantity` already bakes in the *average* weather effect, and unrelated day-to-day volume noise was the same order of magnitude as the weather signal. Fixed by deliberately strengthening `weather.py`'s effect (narrower neutral band, higher precip probability, larger per-category effects) and halving unrelated randomness, then regenerating history and retraining. Result: extreme-temperature service-level gap grew from +0.31pp to +2.0pp. Required a new output path — `run_daily_simulation.py` now writes `data/ab_results_v2.json` instead of overwriting `data/ab_results.json`, which is kept as a frozen pre-retune archive. The Astro site's data-source URL still needs updating to the new filename (out of scope for this repo).
18. **Ingest API retired; simulator writes to Neon directly in 5-min batches (2026-08)** — the always-on FastAPI ingest service (`api/main.py`, `api/routes/events.py`) held a Postgres connection pool open for the life of the systemd process (`pool.SimpleConnectionPool(1, ...)`, eagerly opening a connection at import). Combined with the simulator's own long-lived pooled connection via the same mechanism, this kept Neon's compute endpoint permanently awake — Neon only autosuspends when there are zero active connections — and exhausted the free tier's monthly compute-hour allowance in about a week of continuous 24/7 running, regardless of actual event volume. Fixed by deleting the ingest API entirely (nothing else called it — the dashboard already read Neon directly) and rewriting `pos_simulator.py` to buffer sales/waste/stockout events in memory and flush them every `FLUSH_INTERVAL_SECONDS` (300s, matching the dashboard's own autorefresh cadence so no perceptible staleness is added) via a short-lived `psycopg2` connection per store, opened and closed just for that flush — mirroring the batch-insert pattern `fast_historical_generator.py` already used for backfills. `api/db/connection.py`'s pool remains for the dashboard and one-off scripts only, with `minconn` dropped to 0 so merely importing it doesn't eagerly open a connection. Tradeoff: up to one flush interval's worth of buffered events can be lost if the simulator process dies uncleanly (a clean `KeyboardInterrupt` does a best-effort final flush).
