# Streamlit entry point


import streamlit as st # type:ignore
from dashboard.components.store_selector import store_selector
from dashboard.components.production_plan import production_plan
from dashboard.utils.data_fetch import get_production_plan


st.title('KitchenSync Production Plan')

store_id = store_selector()
df = get_production_plan(store_id)
production_plan(df)