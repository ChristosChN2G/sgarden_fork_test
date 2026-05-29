"""Pydantic models for the order resource."""
from typing import List

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    """A single line item in an order, referencing a product and a quantity."""

    productId: str
    quantity: int = Field(..., ge=1)


class OrderRequest(BaseModel):
    """Request body for creating or replacing an order."""

    items: List[OrderItem] = Field(..., min_length=1)
