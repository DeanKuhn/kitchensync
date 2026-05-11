# FastAPI entry point
# Creates the FastAPI app and tell it about the routes

from fastapi import FastAPI # type:ignore

# Load route file which defines endpoints
from api.routes import events

app = FastAPI()

# Registers loaded routes onto the app
# Add in a prefix /events to the url for each of the events automatically
app.include_router(events.router, prefix="/events")


# ORDER OF HTTP POST /events/store_004/sales
#   -> main.py receives it
#   -> looks up the matching route in events.py
#   -> calls create_sales_event(store_id="store_004", event=...)
#   -> writes to Neon
#   -> returns {"status": "ok", "store_id": "store_004"}