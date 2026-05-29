from fastapi import APIRouter, Depends, HTTPException, status
from database import orders_collection, products_collection
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _parse_date(date_str: str, end_of_day: bool = False) -> datetime:
    """Parse an ISO-format date string into a datetime object.

    When end_of_day is True, the time is set to 23:59:59.999999 so the
    value acts as an inclusive upper bound for date-range queries.
    Raises HTTP 400 with a descriptive message on invalid input.
    """
    try:
        dt = datetime.fromisoformat(date_str)
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: '{date_str}'. Use ISO format e.g. 2024-01-01",
        )


@router.get("/sales")
async def get_sales_analytics(
    current_user: dict = Depends(get_current_user),
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
):
    """Return aggregated sales analytics with an optional date range filter (auth required).

    Computes total revenue, total order count, revenue grouped by month, and
    the top 10 products by quantity sold. When startDate or endDate are
    provided (ISO format), only orders within that range are included.
    """
    pipeline = []

    # Date range match stage
    date_filter = {}
    if startDate:
        date_filter["$gte"] = _parse_date(startDate)
    if endDate:
        date_filter["$lte"] = _parse_date(endDate, end_of_day=True)
    if date_filter:
        pipeline.append({"$match": {"createdAt": date_filter}})

    pipeline.append({
        "$facet": {
            "overall": [
                {
                    "$group": {
                        "_id": None,
                        "totalRevenue": {"$sum": "$total"},
                        "totalOrders": {"$sum": 1},
                    }
                }
            ],
            "byPeriod": [
                {
                    "$group": {
                        "_id": {
                            "$dateToString": {"format": "%Y-%m", "date": "$createdAt"}
                        },
                        "revenue": {"$sum": "$total"},
                    }
                },
                {"$sort": {"_id": 1}},
            ],
            "productItems": [
                {"$unwind": "$items"},
                {
                    "$group": {
                        "_id": "$items.productId",
                        "totalQuantity": {"$sum": "$items.quantity"},
                    }
                },
                {"$sort": {"totalQuantity": -1}},
                {"$limit": 10},
            ],
        }
    })

    result = await orders_collection.aggregate(pipeline).to_list(length=1)
    data = result[0] if result else {}

    overall = data.get("overall", [{}])[0] if data.get("overall") else {}
    by_period = data.get("byPeriod", [])
    product_items = data.get("productItems", [])

    # Enrich top products with name and revenue from current product prices
    top_products = []
    if product_items:
        product_ids = [
            ObjectId(item["_id"])
            for item in product_items
            if item.get("_id") and ObjectId.is_valid(item["_id"])
        ]
        if product_ids:
            products = await products_collection.find(
                {"_id": {"$in": product_ids}}
            ).to_list(length=len(product_ids))
            product_map = {str(p["_id"]): p for p in products}

            for item in product_items:
                pid = item["_id"]
                product = product_map.get(pid, {})
                quantity = item["totalQuantity"]
                price = product.get("price") or 0
                top_products.append({
                    "productId": pid,
                    "name": product.get("name"),
                    "totalQuantity": quantity,
                    "totalRevenue": round(price * quantity, 2),
                })

    return {
        "totalRevenue": round(overall.get("totalRevenue") or 0, 2),
        "totalOrders": overall.get("totalOrders", 0),
        "topProducts": top_products,
        "revenueByPeriod": [
            {"period": p["_id"], "revenue": round(p["revenue"], 2)}
            for p in by_period
        ],
    }
