import streamlit as st # type:ignore


def highlight_cells(row):
    styles = [''] * len(row)

    # Highlight missing units of stockouts
    col_idx = row.index.get_loc('missed_units')
    if row['missed_units'] > 0:
        styles[col_idx] = 'background-color: #ffa500; color: black; font-weight: bold'

    return styles


# Per-store production plan table
def production_plan(df):
    # Initialize session state for the 'Done' list if it doesn't exist
    if "done_items" not in st.session_state:
        st.session_state.done_items = set()

    # Pre-populate the 'done' column based on persistent memory
    df["done"] = df["item_id"].apply(lambda x: x in st.session_state.done_items)
    df_done = df[df['done'] == True]
    df = df[df['done'] == False]

    df["predicted_units"] = df["predicted_units"].round().astype(int)

    df_kitchen = df[df['category'].isin(['sandwich', 'roller_grill', 'side'])]
    df_chicken = df[df['category'].isin(['chicken', 'appetizer'])]

    styled_df_kitchen = df_kitchen.style.apply(highlight_cells, axis=1)
    styled_df_chicken = df_chicken.style.apply(highlight_cells, axis=1)

    # Both interactive production plans
    st.subheader("[Kitchen] Current Production Queue")
    edited_df_kitchen = st.data_editor(
        styled_df_kitchen,
        column_config={
            "done": st.column_config.CheckboxColumn(
                "Complete",
                help="Mark this batch as placed on the warming rack",
                default=False,
            ),
            "item_id": "Item",
            "predicted_units": "Planned",
            "missed_units": st.column_config.NumberColumn(
                "Missed Demand",
                help="Units requested by customers while out of stock"
            ),
            "category": None
        },
        disabled=["item_id", "predicted_units", "missed_units"],
        hide_index=True,
        width='content',
        key="kitchen_prod_plan"
    )

    st.subheader("[Chicken] Current Production Queue")
    edited_df_chicken = st.data_editor(
        styled_df_chicken,
        column_config={
            "done": st.column_config.CheckboxColumn(
                "Complete",
                help="Mark this batch as placed on the warming rack",
                default=False,
            ),
            "item_id": "Item",
            "predicted_units": "Planned",
            "missed_units": st.column_config.NumberColumn(
                "Missed Demand",
                help="Units requested by customers while out of stock"
            ),
            "category": None
        },
        disabled=["item_id", "predicted_units", "missed_units"],
        hide_index=True,
        width='content',
        key="chicken_prod_plan"
    )

    st.subheader("Completed Items")
    edited_df_done = st.dataframe(
        df_done,
        column_config={
            "item_id": "Item",
            "predicted_units": "Cooked",
            "missed_units": None,
            "category": None,
            "done": None
        },
        hide_index=True
    )

    # Check which items were marked as done in this session
    current_done_kitchen = \
        set(edited_df_kitchen[edited_df_kitchen["done"] == True]["item_id"])

    current_done_chicken = \
        set(edited_df_chicken[edited_df_chicken["done"] == True]["item_id"])

    # Update our persistent state
    st.session_state.done_items.update(current_done_kitchen)
    st.session_state.done_items.update(current_done_chicken)

    # Feedback for the user
    if current_done_kitchen:
        st.success(f"Production acknowledged for {len(current_done_kitchen)} items.")
    if current_done_chicken:
        st.success(f"Production acknowledged for {len(current_done_chicken)} items.")