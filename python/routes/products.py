from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import JSONResponse
import asyncio
from pydantic import BaseModel
from models.product import ProductRequest
from database import products_collection
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime
from typing import Optional


router = APIRouter(prefix="/api/products", tags=["products"])


class StockUpdateRequest(BaseModel):
    stock: int


# CODE QUALITY ISSUE: unused variable
service_name = "ProductService"


def product_to_response(product: dict) -> dict:
    """Convert MongoDB document to API response format."""
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": (
            product.get("createdAt", "").isoformat()
            if product.get("createdAt") else None
        ),
        "updatedAt": (
            product.get("updatedAt", "").isoformat()
            if product.get("updatedAt") else None
        ),
    }


def format_product(product: dict) -> dict:
    """CODE QUALITY ISSUE: duplicate of product_to_response above."""
    return {
        "id": str(product["_id"]),
        "name": product.get("name"),
        "description": product.get("description"),
        "category": product.get("category"),
        "price": product.get("price"),
        "stock": product.get("stock", 0),
        "createdAt": (
            product.get("createdAt", "").isoformat()
            if product.get("createdAt") else None
        ),
        "updatedAt": (
            product.get("updatedAt", "").isoformat()
            if product.get("updatedAt") else None
        ),
    }


_ALLOWED_SORT_FIELDS = {"name", "price", "category", "stock", "createdAt", "updatedAt"}
_VALID_CATEGORIES = {"Electronics", "Accessories", "Storage", "Networking"}


def _validate_product(request: ProductRequest, is_create: bool = False) -> dict:
    errors = {}
    if is_create and not (request.name and request.name.strip()):
        errors["name"] = "name is required"
    if request.price is not None and request.price <= 0:
        errors["price"] = "price must be a positive number"
    if request.category is not None and request.category not in _VALID_CATEGORIES:
        errors["category"] = f"category must be one of: {', '.join(sorted(_VALID_CATEGORIES))}"
    return errors


@router.get("")
async def get_all_products(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    sort: Optional[str] = None,
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    skip = (page - 1) * limit
    sort_direction = -1 if order == "desc" else 1

    cursor = products_collection.find()
    if sort and sort in _ALLOWED_SORT_FIELDS:
        cursor = cursor.sort(sort, sort_direction)
    cursor = cursor.skip(skip).limit(limit)

    total, product_docs = await asyncio.gather(
        products_collection.count_documents({}),
        cursor.to_list(length=limit),
    )

    return {
        "data": [product_to_response(p) for p in product_docs],
        "page": page,
        "limit": limit,
        "total": total,
    }


@router.get("/search")
async def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    minPrice: Optional[float] = None,
    maxPrice: Optional[float] = None,
):
    query: dict = {}

    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
        ]

    if category is not None:
        query["category"] = category

    if minPrice is not None or maxPrice is not None:
        price_filter: dict = {}
        if minPrice is not None:
            price_filter["$gte"] = minPrice
        if maxPrice is not None:
            price_filter["$lte"] = maxPrice
        query["price"] = price_filter

    products = []
    async for product in products_collection.find(query):
        products.append(product_to_response(product))

    return products


@router.get("/stats")
async def get_product_stats():
    pipeline = [
        {
            "$facet": {
                "overall": [
                    {
                        "$group": {
                            "_id": None,
                            "totalCount": {"$sum": 1},
                            "averagePrice": {"$avg": "$price"},
                            "minPrice": {"$min": "$price"},
                            "maxPrice": {"$max": "$price"},
                        }
                    }
                ],
                "byCategory": [
                    {"$group": {"_id": "$category", "count": {"$sum": 1}}}
                ],
            }
        }
    ]

    result = await products_collection.aggregate(pipeline).to_list(length=1)
    data = result[0] if result else {}

    overall = data.get("overall", [{}])[0] if data.get("overall") else {}
    by_category = data.get("byCategory", [])

    return {
        "totalCount": overall.get("totalCount", 0),
        "averagePrice": round(overall.get("averagePrice") or 0, 2),
        "minPrice": overall.get("minPrice", 0),
        "maxPrice": overall.get("maxPrice", 0),
        "categoryCount": {(item["_id"] or "Uncategorized"): item["count"] for item in by_category},
    }


@router.get("/{product_id}")
async def get_product_by_id(product_id: str):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return product_to_response(product)


@router.patch("/{product_id}/stock")
async def update_stock(
    product_id: str,
    request: StockUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    if request.stock < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stock must be a non-negative number",
        )

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"stock": request.stock, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(request: ProductRequest, current_user: dict = Depends(get_current_user)):
    errors = _validate_product(request, is_create=True)
    if errors:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Validation failed", "errors": errors},
        )

    product_doc = {
        "name": request.name,
        "description": request.description,
        "category": request.category,
        "price": request.price,
        "stock": request.stock if request.stock is not None else 0,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }

    result = await products_collection.insert_one(product_doc)
    product_doc["_id"] = result.inserted_id
    print(f"Created product: {request.name}")
    return product_to_response(product_doc)


async def update_product_legacy(
    product_id: str,
    request: ProductRequest,
    current_user: dict = Depends(get_current_user),
):
    """CODE QUALITY ISSUE: duplicate of update_product."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.put("/{product_id}")
async def update_product(
    product_id: str,
    request: ProductRequest,
    current_user: dict = Depends(get_current_user),
):
    errors = _validate_product(request, is_create=False)
    if errors:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Validation failed", "errors": errors},
        )

    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    update_fields = {}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.description is not None:
        update_fields["description"] = request.description
    if request.category is not None:
        update_fields["category"] = request.category
    if request.price is not None:
        update_fields["price"] = request.price
    if request.stock is not None:
        update_fields["stock"] = request.stock

    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    update_fields["updatedAt"] = datetime.utcnow()

    result = await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_fields},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return product_to_response(product)


@router.delete("/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await products_collection.delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return {"message": "Product deleted"}
