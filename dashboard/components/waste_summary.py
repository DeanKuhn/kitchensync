# Waste metrics per category starting new each day

import streamlit as st # type:ignore


def waste_summary(df):

    # Filter category
    hot_foods = df[(df['category'].isin(['sandwich', 'side']))]

    chicken = df[(df['category'].isin(['chicken', 'appetizer']))]

    roller_grill = df[(df['category'] == 'roller_grill')]

    # --- HOT FOODS ---
    if hot_foods['sale_revenue'].sum() == 0:
        hot_foods_waste = 'N/A'
        hot_foods_sale = 'N/A'
        hot_foods_quantity = 0
    else:
        hot_foods_waste = \
            (hot_foods['waste_cost'].sum() /
             hot_foods['sale_revenue'].sum()) * 100
        hot_foods_sale = hot_foods['sale_revenue'].sum()
        hot_foods_quantity = hot_foods['sale_quantity'].sum()

    # --- ROLLER GRILL ---
    if roller_grill['sale_revenue'].sum() == 0:
        roller_grill_waste = 'N/A'
        roller_grill_sale = 'N/A'
        roller_grill_quantity = 0
    else:
        roller_grill_waste = \
            (roller_grill['waste_cost'].sum() /
             roller_grill['sale_revenue'].sum()) * 100
        roller_grill_sale = roller_grill['sale_revenue'].sum()
        roller_grill_quantity = roller_grill['sale_quantity'].sum()

    # --- CHICKEN ---
    if chicken['sale_revenue'].sum() == 0:
        chicken_waste = 'N/A'
        chicken_sale = 'N/A'
        chicken_quantity = 0
    else:
        chicken_waste = \
            (chicken['waste_cost'].sum() /
             chicken['sale_revenue'].sum()) * 100
        chicken_sale = chicken['sale_revenue'].sum()
        chicken_quantity = chicken['sale_quantity'].sum()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Hot Foods Units",
            value=f"{hot_foods_quantity}")
        st.metric(label="Hot Foods Sales",
            value=f"${hot_foods_sale:.2f}" if hot_foods_sale != 'N/A' else 'N/A')
        st.metric(label="Hot Foods Waste",
            value=f"{hot_foods_waste:.1f}%" if hot_foods_waste != 'N/A' else 'N/A')
    with col2:
        st.metric(label="Roller Grill Units",
            value=f"{roller_grill_quantity}")
        st.metric(label="Roller Grill Sales",
            value=f"${roller_grill_sale:.2f}" if roller_grill_sale != 'N/A' else 'N/A')
        st.metric(label="Roller Grill Waste",
            value=f"{roller_grill_waste:.1f}%" if roller_grill_waste != 'N/A' else 'N/A')
    with col3:
        st.metric(label="Chicken Units",
            value=f"{chicken_quantity}")
        st.metric(label="Chicken Sales",
            value=f"${chicken_sale:.2f}" if chicken_sale != 'N/A' else 'N/A')
        st.metric(label="Chicken Waste",
            value=f"{chicken_waste:.1f}%" if chicken_waste != 'N/A' else 'N/A')