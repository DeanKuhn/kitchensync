# Streamlit entry point


import os
import sys

# Ensure the repo root is importable regardless of how the app is launched
# (locally we rely on PYTHONPATH=., but hosted runners like Streamlit
# Community Cloud invoke `streamlit run dashboard/app.py` directly).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st # type:ignore
from streamlit_autorefresh import st_autorefresh # type:ignore
from dashboard.components.store_selector import store_selector
from dashboard.components.production_plan import production_plan
from dashboard.components.waste_summary import waste_summary
from dashboard.utils.data_fetch import \
    get_production_plan, get_waste_summary, get_sim_now, get_today_start

# --- LIVE REFRESH ---
# Refresh every 5 minutes since the pos simulator extracts to Snowflake every
# 5 minutes
st_autorefresh(interval=300000, key="datarefresh")

st.set_page_config(page_title="KitchenSync Dashboard", layout="wide")
st.title('KitchenSync Production Plan')

store_id = store_selector()
now = get_sim_now(store_id)
today_start = get_today_start(now)
df = get_production_plan(store_id, now, today_start)
st.caption(f"Predicting for: {df.attrs['predicted_for'].strftime('%A %I:%M %p %Z')}")
production_plan(df)

df_waste = get_waste_summary(store_id, now, today_start)
waste_summary(df_waste)