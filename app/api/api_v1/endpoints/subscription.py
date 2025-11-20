import base64
from fastapi import APIRouter, HTTPException
from app.models.user import User
from app.services.vpn_service import vpn_service

router = APIRouter()

@router.get("/{user_token}")
async def get_subscription(user_token: str):
    """Get unified subscription with all user configs"""
    
    # Get user
    user = await User.find_one(User.subscription_token == user_token)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Auto-sync all subscriptions to new panels
    for sub_link in user.subscriptions:
        subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if subscription and subscription.is_active:
            await vpn_service.sync_subscription_to_new_panels(subscription)
    
    # Get all config URLs for user using VPN service
    all_configs = await vpn_service.get_user_configs(user_token)
    
    if not all_configs:
        raise HTTPException(status_code=404, detail="No active configs found")
    
    # Return base64 encoded configs (V2Ray standard)
    configs_text = "\n".join(all_configs)
    return base64.b64encode(configs_text.encode()).decode()