import base64
from fastapi import APIRouter, HTTPException
from app.models.user import User
from app.services.vpn_service import vpn_service

router = APIRouter()

@router.get("/{subscription_token}")
async def get_subscription(subscription_token: str, format: str = "base64"):
    """Get subscription configs by token
    
    Args:
        subscription_token: Subscription token
        format: Response format - 'base64' (default, V2Ray standard) or 'json'
    """
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
    
    # Return based on format
    if format.lower() == "json":
        return {
            "subscription_token": subscription_token,
            "configs": all_configs,
            "total_configs": len(all_configs)
        }
    else:
        # Return base64 encoded configs (V2Ray standard)
        configs_text = "\n".join(all_configs)
        return base64.b64encode(configs_text.encode()).decode()