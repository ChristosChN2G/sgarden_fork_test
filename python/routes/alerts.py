from fastapi import APIRouter, Depends
from database import products_collection, settings_collection
from security.jwt_handler import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_DEFAULT_THRESHOLD = 10
_THRESHOLD_KEY = "alert_threshold"


class ThresholdRequest(BaseModel):
    threshold: int


def _severity(stock: int, threshold: int) -> str:
    if stock <= threshold // 4:
        return "critical"
    if stock <= threshold // 2:
        return "warning"
    return "info"


async def _get_threshold() -> int:
    doc = await settings_collection.find_one({"key": _THRESHOLD_KEY})
    return doc["value"] if doc else _DEFAULT_THRESHOLD


@router.get("")
async def get_alerts(current_user: dict = Depends(get_current_user)):
    threshold = await _get_threshold()
    cursor = products_collection.find({"stock": {"$lt": threshold}})
    alerts = []
    async for product in cursor:
        stock = product.get("stock", 0)
        alerts.append({
            "productId": str(product["_id"]),
            "productName": product.get("name"),
            "stock": stock,
            "threshold": threshold,
            "severity": _severity(stock, threshold),
        })
    return alerts


@router.put("/threshold")
async def set_threshold(request: ThresholdRequest, current_user: dict = Depends(get_current_user)):
    await settings_collection.update_one(
        {"key": _THRESHOLD_KEY},
        {"$set": {"key": _THRESHOLD_KEY, "value": request.threshold}},
        upsert=True,
    )
    return {"threshold": request.threshold}
