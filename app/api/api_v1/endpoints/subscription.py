import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from app.models.user import User
from app.services.vpn_service import vpn_service

router = APIRouter()

@router.get("/{subscription_token}", response_class=PlainTextResponse)
async def get_subscription(subscription_token: str):
    """Get subscription configs by token (base64 encoded)"""
    from app.models.subscription import Subscription
    
    # Get subscription
    subscription = await Subscription.find_one(Subscription.subscription_token == subscription_token)
    if not subscription or not subscription.is_active:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Auto-sync subscription to new panels
    await vpn_service.sync_subscription_to_new_panels(subscription)
    
    # Get all config URLs for this subscription
    all_configs = await vpn_service.get_user_configs(subscription_token)
    
    if not all_configs:
        raise HTTPException(status_code=404, detail="No active configs found")
    
    # Return base64 encoded configs (standard subscription format)
    configs_text = "\n".join(all_configs)
    return base64.b64encode(configs_text.encode()).decode()