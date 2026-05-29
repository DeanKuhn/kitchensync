# Streamlit entry point


import streamlit as st # type:ignore
from streamlit_autorefresh import st_autorefresh # type:ignore
from dashboard.components.store_selector import store_selector
from dashboard.components.production_plan import production_plan
from dashboard.components.waste_summary import waste_summary
from dashboard.utils.data_fetch import get_production_plan, get_waste_summary

# --- LIVE REFRESH ---
# Refresh every 5 minutes since the pos simulator extracts to Snowflake every
# 5 minutes
st_autorefresh(interval=300000, key="datarefresh")

st.set_page_config(page_title="KitchenSync Dashboard", layout="wide")
st.title('KitchenSync Production Plan')

store_id = store_selector()
df = get_production_plan(store_id)
production_plan(df)

df_waste = get_waste_summary(store_id)
waste_summary(df_waste)