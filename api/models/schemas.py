from pydantic import BaseModel
from datetime import datetime

class SalesEvent(BaseModel):
    item_id: str
    quantity: int
    price: float
    created_at: datetime

class WasteEvent(BaseModel):
    item_id: str
    quantity: int
    created_at: datetime

class StockoutEvent(BaseModel):
    item_id: str
    quantity_requested: int
    created_at: datetime