# Store selector dropdown in streamlit

import yaml # type:ignore
import streamlit as st # type:ignore

with open("config/stores.yaml") as f:
    config = yaml.safe_load(f)

stores = []

for store in config["stores"]:
    stores.append(store["id"])


def store_selector():
    return st.sidebar.selectbox("Select a store", stores)