from pydantic import BaseModel, Field
from typing import List


class OrderItem(BaseModel):
    productId: str
    quantity: int = Field(..., ge=1)


class OrderRequest(BaseModel):
    items: List[OrderItem] = Field(..., min_length=1)
