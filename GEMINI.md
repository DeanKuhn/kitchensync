# GEMINI.md — Project State & Senior Engineer Handover

This file serves as the authoritative reference for the current architectural state and development history following the May 2026 "Senior Engineer Overhaul."

---

## Architecture Overview (Post-Overhaul)

### 1. Ingest Layer (FastAPI + Neon)
- **Status**: Production-ready.
- **Endpoints**: `/sales`, `/waste`, `/stockout`.
- **Database**: Per-store Postgres schemas in Neon. 
- **Stockout Tracking**: Recently added "First-Class" event tracking for missed demand.
- **Critical Fix**: SQL syntax error in `waste_log` insertion was corrected.

### 2. POS Simulator (The Engine)
- **Core**: Refactored to `asyncio` and `httpx` for extreme scalability.
- **Stochastic Modeling**: Uses **Poisson Distribution** (`numpy.random.poisson`) for realistic customer arrival.
- **Kitchen State**: Implemented `StoreState` class with **FIFO Batch Management**.
- **Replenishment**: Moved from hourly jumps to a **15-minute sliding window**. It now follows the `MART_PRODUCTION_TARGETS` built in dbt.

### 3. Analytics Layer (Snowflake + dbt)
- **Medallion Logic**: Staging (Cleaning), Intermediate (Features), Marts (Business Logic).
- **Golden Model**: `mart_production_targets.sql`. 
    - Uses a **Double-Union Self-Join** to handle week-end wrap-around.
    - Calculates prescriptive inventory targets based on item-specific `hold_time`.
- **Data Quality**: Integrated `dbt-utils` for range and null testing.
- **Visualization**: Every SQL model contains a `/* DATA TRANSFORMATION VISUALIZATION */` block for instant auditing.

### 4. Operational UI (Streamlit)
- **Features**: Interactive "Kitchen Queue" using `st.data_editor`.
- **State**: Persistent session state (`st.session_state`) ensures "Mark Done" checkmarks survive auto-refreshes.
- **Live Refresh**: Dashboard polls Snowflake every 60 seconds.
- **Logic**: Joined predictions with real-time stockout data to surface "Missed Demand" alerts in orange.

---

## Development Environment (WSL + uv)

- **Parity**: The project is strictly managed via **WSL (Linux)** to ensure compatibility with LightGBM and dbt-snowflake.
- **Dependency Management**: `pyproject.toml` is the source of truth. 
- **Key Packages Added**: `dbt-core`, `dbt-snowflake`, `python-dotenv`, `psycopg2-binary`, `requests`, `streamlit-autorefresh`.

---

## Project Context & "Senior" Conventions

1.  **Uniformity**: All dbt models must have column-level documentation in `models.yml` and a visualization block in the SQL file.
2.  **Casting**: Always use explicit casting (`::integer`, `::timestamp`) in Snowflake queries to prevent implicit performance hits.
3.  **Encapsulation**: Simulator logic should remain inside classes (like `StoreState`) to maintain clean separation of concerns.

---

## Pending Next Steps (The "Flywheel" Run)

To resume the system, execute the following in order:

1.  **Run Pipeline**: `uv run python -m scripts.run_pipeline` 
    - This will Extract Neon data, Run dbt, and Refresh ML predictions.
2.  **Start Simulator**: `uv run python simulator/pos_simulator.py`
3.  **Start Dashboard**: `uv run streamlit run dashboard/app.py`

---

## Interview Highlights (The Pitch)
- **"Just-In-Time Production"**: Explain the sliding 15-minute window targets.
- **"Stochastic POS"**: Explain the Poisson arrival modeling.
- **"Demand Capture"**: Explain why we track stockouts to measure lost opportunity cost.
- **"Stateful Dashboard"**: Explain session persistence in Streamlit.
