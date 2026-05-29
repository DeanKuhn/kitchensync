from fastapi import APIRouter, HTTPException # type:ignore
from api.models.schemas import SalesEvent, WasteEvent, StockoutEvent
from api.db.connection import get_store_connection, release_connection

router = APIRouter()


def close_and_commit(connection, cursor):
    connection.commit()
    cursor.close()
    release_connection(connection)


def close_not_commit(connection, cursor):
    cursor.close()
    release_connection(connection)


@router.post("/{store_id}/sales")
def create_sales_event(store_id: str, event: SalesEvent):

    # Establish connection to the right store based on store id
    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO sales_events (item_id, quantity, price, created_at)
            VALUES (%s, %s, %s, %s);
        """, (event.item_id, event.quantity, event.price, event.created_at))

        close_and_commit(connection, cursor)
        return {"status": "ok", "store_id": store_id}

    except Exception as e:
        close_not_commit(connection, cursor)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{store_id}/waste")
def create_waste_event(store_id: str, event: WasteEvent):

    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT into waste_log (item_id, quantity, created_at)
            VALUES (%s, %s, %s);
        """, (event.item_id, event.quantity, event.created_at))

        close_and_commit(connection, cursor)
        return {"status": "ok", "store_id": store_id}

    except Exception as e:
        close_not_commit(connection, cursor)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{store_id}/stockout")
def create_stockout_event(store_id: str, event: StockoutEvent):

    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT into stockout_events (item_id, quantity_requested, created_at)
            VALUES (%s, %s, %s);
        """, (event.item_id, event.quantity_requested, event.created_at))

        close_and_commit(connection, cursor)
        return {"status": "ok", "store_id": store_id}

    except Exception as e:
        close_not_commit(connection, cursor)
        raise HTTPException(status_code=500, detail=str(e))