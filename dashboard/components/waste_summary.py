# Waste metrics per category starting new each day

import streamlit as st # type:ignore

def waste_summary(df):

    # Filter category
    hot_foods = df[(df['area'] == 'hot_spot') &
        (~df['category'].isin(['chicken', 'appetizers', 'sides']))]

    chicken = df[(df['area'] == 'hot_spot') &
        (df['category'].isin(['chicken', 'appetizers', 'sides']))]

    roller_grill = df[(df['area'] == 'roller_grill')]

    if hot_foods['sale_revenue'].sum() == 0:
        hot_foods_pct = 'N/A'
    else:
        hot_foods_pct = \
            (hot_foods['waste_cost'].sum() /
             hot_foods['sale_revenue'].sum()) * 100

    if chicken['sale_revenue'].sum() == 0:
        chicken_pct = 'N/A'
    else:
        chicken_pct = \
            (chicken['waste_cost'].sum() /
             chicken['sale_revenue'].sum()) * 100

    if roller_grill['sale_revenue'].sum() == 0:
        roller_grill_pct = 'N/A'
    else:
        roller_grill_pct = \
            (roller_grill['waste_cost'].sum() /
            roller_grill['sale_revenue'].sum()) * 100

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Hot Foods",
            value=f"{hot_foods_pct:.1f}%" if hot_foods_pct != 'N/A' else 'N/A')
    with col2:
        st.metric(label="Roller Grill",
            value=f"{roller_grill_pct:.1f}%" if roller_grill_pct != 'N/A' else 'N/A')
    with col3:
        st.metric(label="Chicken",
            value=f"{chicken_pct:.1f}%" if chicken_pct != 'N/A' else 'N/A')