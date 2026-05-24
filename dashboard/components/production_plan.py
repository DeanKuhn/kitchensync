# Per-store production plan table

import streamlit as st # type:ignore

# Make urgent rows red
def highlight_urgency(row):
    if row['urgency_flag'] == 'URGENT':
        return ['background-color: red'] * len(row)
    return [''] * len(row)


def production_plan(df):
    styled = df.style.apply(highlight_urgency, axis=1)
    st.dataframe(styled)