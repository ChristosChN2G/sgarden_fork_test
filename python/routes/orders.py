from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from database import orders_collection, products_collection
from models.order import OrderItem, OrderRequest
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])

_VALID_TRANSITIONS = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"shipped"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


class StatusUpdateRequest(BaseModel):
    """Request body for transitioning an order to a new status."""

    status: str


def order_to_response(order: dict) -> dict:
    """Convert a MongoDB order document to API response format.

    Serialises ObjectId to string and formats datetime fields as ISO strings.
    """
    return {
        "id": str(order["_id"]),
        "items": order.get("items", []),
        "total": order.get("total", 0),
        "status": order.get("status", "pending"),
        "createdAt": order["createdAt"].isoformat() if order.get("createdAt") else None,
        "updatedAt": order["updatedAt"].isoformat() if order.get("updatedAt") else None,
    }


async def calculate_total(items: List[OrderItem]) -> float:
    """Calculate the total price for a list of order items.

    Fetches current product prices from the database and multiplies each
    by the requested quantity. Items with invalid or missing product IDs
    contribute 0 to the total. Returns the result rounded to 2 decimal places.
    """
    valid_ids = [
        ObjectId(item.productId)
        for item in items
        if ObjectId.is_valid(item.productId)
    ]
    products = await products_collection.find(
        {"_id": {"$in": valid_ids}}
    ).to_list(length=len(valid_ids))
    price_map = {str(p["_id"]): p.get("price", 0) for p in products}
    return round(sum(price_map.get(item.productId, 0) * item.quantity for item in items), 2)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(request: OrderRequest, _current_user: dict = Depends(get_current_user)):
    """Create a new order and decrement product stock (auth required).

    Validates that all referenced products exist and have sufficient stock
    before committing. Raises HTTP 400 if any product is not found or stock
    is insufficient.
    """
    valid_ids = [
        ObjectId(item.productId)
        for item in request.items
        if ObjectId.is_valid(item.productId)
    ]
    products = await products_collection.find(
        {"_id": {"$in": valid_ids}}
    ).to_list(length=len(valid_ids))
    product_map = {str(p["_id"]): p for p in products}

    for item in request.items:
        product = product_map.get(item.productId)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {item.productId} not found",
            )
        if product.get("stock", 0) < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient stock for product {item.productId}: "
                    f"available {product.get('stock', 0)}, "
                    f"requested {item.quantity}"
                ),
            )

    for item in request.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.productId)},
            {"$inc": {"stock": -item.quantity}, "$set": {"updatedAt": datetime.utcnow()}},
        )

    price_map = {str(p["_id"]): p.get("price", 0) for p in products}
    total = round(
        sum(
            price_map.get(item.productId, 0) * item.quantity
            for item in request.items
        ),
        2,
    )

    order_doc = {
        "items": [item.model_dump() for item in request.items],
        "total": total,
        "status": "pending",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return order_to_response(order_doc)


@router.get("")
async def get_all_orders(
    _current_user: dict = Depends(get_current_user),
    status_filter: Optional[str] = Query(default=None, alias="status"),
):
    """Return all orders, optionally filtered by status (auth required).

    When the status query parameter is provided only matching orders are
    returned; omitting it returns every order.
    """
    query = {"status": status_filter} if status_filter else {}
    orders = await orders_collection.find(query).to_list(length=None)
    return [order_to_response(o) for o in orders]


@router.get("/{order_id}")
async def get_order(order_id: str, _current_user: dict = Depends(get_current_user)):
    """Return a single order by its MongoDB ObjectId (auth required).

    Raises HTTP 404 if the ID is invalid or the order does not exist.
    """
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return order_to_response(order)


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    request: StatusUpdateRequest,
    _current_user: dict = Depends(get_current_user),
):
    """Transition an order to a new status following the allowed workflow (auth required).

    Valid transitions: pending → confirmed/cancelled, confirmed → shipped,
    shipped → delivered. Raises HTTP 400 for invalid transitions and HTTP 404
    if the order does not exist.
    """
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    current_status = order.get("status", "pending")
    new_status = request.status

    if new_status not in _VALID_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{current_status}' to '{new_status}'",
        )

    await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": new_status, "updatedAt": datetime.utcnow()}},
    )

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return order_to_response(order)


@router.put("/{order_id}")
async def update_order(
    order_id: str,
    request: OrderRequest,
    _current_user: dict = Depends(get_current_user),
):
    """Replace the items of an existing order and recalculate the total (auth required).

    Raises HTTP 404 if the order does not exist.
    """
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    total = await calculate_total(request.items)
    update_fields = {
        "items": [item.model_dump() for item in request.items],
        "total": total,
        "updatedAt": datetime.utcnow(),
    }

    result = await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return order_to_response(order)


@router.delete("/{order_id}")
async def delete_order(order_id: str, _current_user: dict = Depends(get_current_user)):
    """Permanently delete an order by ID (auth required).

    Raises HTTP 404 if the order does not exist.
    """
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    result = await orders_collection.delete_one({"_id": ObjectId(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return {"message": "Order deleted"}
