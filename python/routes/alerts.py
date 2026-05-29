from fastapi import APIRouter
from pydantic import BaseModel

from database import products_collection, settings_collection

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_DEFAULT_THRESHOLD = 10
_THRESHOLD_KEY = "alert_threshold"


class ThresholdRequest(BaseModel):
    """Request body for updating the low-stock alert threshold."""

    threshold: int


def _severity(stock: int, threshold: int) -> str:
    """Return the alert severity level based on current stock vs threshold.

    Levels:
    - critical: stock is at or below 25% of the threshold
    - warning:  stock is at or below 50% of the threshold
    - info:     stock is below the threshold but above 50%
    """
    if stock <= threshold // 4:
        return "critical"
    if stock <= threshold // 2:
        return "warning"
    return "info"


async def _get_threshold() -> int:
    """Retrieve the current low-stock alert threshold from the database.

    Falls back to _DEFAULT_THRESHOLD if no value has been configured yet.
    """
    doc = await settings_collection.find_one({"key": _THRESHOLD_KEY})
    return doc["value"] if doc else _DEFAULT_THRESHOLD


@router.get("")
async def get_alerts():
    """Return a list of products whose stock is below the alert threshold.

    Each entry includes the product ID, name, current stock, the active
    threshold, and a severity level (critical / warning / info).
    """
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
async def set_threshold(request: ThresholdRequest):
    """Update the low-stock alert threshold stored in the database.

    Uses an upsert so the setting is created on first call if it does not
    exist yet. Returns the newly applied threshold value.
    """
    await settings_collection.update_one(
        {"key": _THRESHOLD_KEY},
        {"$set": {"key": _THRESHOLD_KEY, "value": request.threshold}},
        upsert=True,
    )
    return {"threshold": request.threshold}
