"""Pydantic models for the product resource.

Defines the MongoDB document shape (ProductInDB), the request body for
create/update operations (ProductRequest), and the API response shape
(ProductResponse). V2 variants are duplicates kept for backward compatibility.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProductInDB(BaseModel):
    """MongoDB document shape for a product, as stored in the database."""

    id: Optional[str] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProductRequest(BaseModel):
    """Request body for creating or updating a product.

    All fields are optional to support partial updates (PUT).
    """

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None


class ProductResponse(BaseModel):
    """API response shape for a product returned to the client."""

    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class ProductInDBV2(BaseModel):
    """MongoDB document shape for a product, as stored in the database.

    CODE QUALITY ISSUE: duplicate of ProductInDB — should be removed and all
    references migrated to ProductInDB.
    """
    id: Optional[str] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProductRequestV2(BaseModel):
    """Request body for creating or updating a product.

    CODE QUALITY ISSUE: duplicate of ProductRequest — should be removed and
    all references migrated to ProductRequest.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None


class ProductResponseV2(BaseModel):
    """API response shape for a product returned to the client.

    CODE QUALITY ISSUE: duplicate of ProductResponse — should be removed and
    all references migrated to ProductResponse.
    """
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
