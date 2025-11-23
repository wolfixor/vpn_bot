"""
Migration API Endpoints
Admin endpoints for managing user migrations between panels
"""

from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel


router = APIRouter(prefix="/migration", tags=["migration"])


class MigrateSubscriptionRequest(BaseModel):
    subscription_token: str
    target_panel_key: str
    reset_traffic: bool = True


class BulkMigrateRequest(BaseModel):
    subscription_tokens: List[str]
    target_panel_key: str
    reset_traffic: bool = True


@router.post("/subscription")
async def migrate_subscription(
    request: MigrateSubscriptionRequest
):
    """Migrate a single subscription between panels"""
    from app.models.subscription import Subscription
    from app.services.migration_service import migration_service
    
    subscription = await Subscription.find_one(Subscription.subscription_token == request.subscription_token)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    result = await migration_service.migrate_subscription(
        subscription,
        request.target_panel_key,
        request.reset_traffic
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.post("/bulk")
async def bulk_migrate(
    request: BulkMigrateRequest
):
    """Migrate multiple subscriptions between panels"""
    from app.services.migration_service import migration_service
    
    result = await migration_service.bulk_migrate_subscriptions(
        request.subscription_tokens,
        request.target_panel_key,
        request.reset_traffic
    )
    
    return result


@router.post("/auto-balance")
async def auto_balance_panels():
    """Automatically balance subscriptions across all panels"""
    from app.services.migration_service import migration_service
    
    result = await migration_service.auto_balance_panels()
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@router.get("/stats")
async def get_migration_stats():
    """Get migration and panel distribution statistics"""
    from app.services.migration_service import migration_service
    
    result = await migration_service.get_migration_stats()
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result