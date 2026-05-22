from fastapi import APIRouter, HTTPException, status, Depends
from database import orders_collection, products_collection
from security.jwt_handler import get_current_user
from models.order import OrderRequest, OrderItem
from bson import ObjectId
from datetime import datetime
from typing import List

router = APIRouter(prefix="/api/orders", tags=["orders"])


def order_to_response(order: dict) -> dict:
    return {
        "id": str(order["_id"]),
        "items": order.get("items", []),
        "total": order.get("total", 0),
        "createdAt": order["createdAt"].isoformat() if order.get("createdAt") else None,
        "updatedAt": order["updatedAt"].isoformat() if order.get("updatedAt") else None,
    }


async def calculate_total(items: List[OrderItem]) -> float:
    valid_ids = [ObjectId(item.productId) for item in items if ObjectId.is_valid(item.productId)]
    products = await products_collection.find({"_id": {"$in": valid_ids}}).to_list(length=len(valid_ids))
    price_map = {str(p["_id"]): p.get("price", 0) for p in products}
    return round(sum(price_map.get(item.productId, 0) * item.quantity for item in items), 2)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(request: OrderRequest, current_user: dict = Depends(get_current_user)):
    valid_ids = [ObjectId(item.productId) for item in request.items if ObjectId.is_valid(item.productId)]
    products = await products_collection.find({"_id": {"$in": valid_ids}}).to_list(length=len(valid_ids))
    product_map = {str(p["_id"]): p for p in products}

    for item in request.items:
        product = product_map.get(item.productId)
        if not product:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {item.productId} not found")
        if product.get("stock", 0) < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for product {item.productId}: available {product.get('stock', 0)}, requested {item.quantity}",
            )

    for item in request.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.productId)},
            {"$inc": {"stock": -item.quantity}, "$set": {"updatedAt": datetime.utcnow()}},
        )

    price_map = {str(p["_id"]): p.get("price", 0) for p in products}
    total = round(sum(price_map.get(item.productId, 0) * item.quantity for item in request.items), 2)

    order_doc = {
        "items": [item.model_dump() for item in request.items],
        "total": total,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return order_to_response(order_doc)


@router.get("")
async def get_all_orders(current_user: dict = Depends(get_current_user)):
    orders = await orders_collection.find().to_list(length=None)
    return [order_to_response(o) for o in orders]


@router.get("/{order_id}")
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return order_to_response(order)


@router.put("/{order_id}")
async def update_order(order_id: str, request: OrderRequest, current_user: dict = Depends(get_current_user)):
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
async def delete_order(order_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(order_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    result = await orders_collection.delete_one({"_id": ObjectId(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    return {"message": "Order deleted"}
