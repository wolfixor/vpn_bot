from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
import json
import httpx
from app.models.vpn_plan import VPNPlan
from app.models.order import Order
from app.services.vpn_service import vpn_service
from app.services.xui_service import XUIService
from app.core.security import verify_token



router = APIRouter()

@router.get("/plans", response_model=List[VPNPlan])
async def get_vpn_plans(token: str = Depends(verify_token)):
    """Get all active VPN plans"""
    plans = await VPNPlan.find(VPNPlan.is_active == True).to_list()
    return plans


@router.post("/plans/seed")
async def set_vpn_plans(token: str = Depends(verify_token)):
    sample_plans = [
        {
            "name": "پلن برنزی",
            "duration_days": 30,
            "price": 250000,
            "traffic_limit_gb": 100,
            "is_active": True
        },        
        {
            "name": "پلن نقره‌ای",
            "duration_days": 90,
            "price": 500000,
            "traffic_limit_gb": 200,
            "is_active": True
        },
        {
            "name": "پلن طلایی",
            "duration_days": 180,
            "price": 1200000,
            "traffic_limit_gb": 500,
            "is_active": True
        }
    ]

    plan_models = [VPNPlan(**plan) for plan in sample_plans]

    result = await VPNPlan.insert_many(plan_models)

    return {
        "message": "Sample VPN plans seeded successfully.",
        "inserted_ids": [str(id) for id in result.inserted_ids]
    }


@router.post("/create/{order_id}")
async def create_vpn_config(order_id: str, delivery_type: str = "subscription", token: str = Depends(verify_token)):
    """Create VPN configuration for an order with multi-panel support"""
    try:
        from bson import ObjectId
        if ObjectId.is_valid(order_id):
            order = await Order.get(ObjectId(order_id))
        else:
            order = await Order.find_one(Order.id == order_id)
    except:
        order = None
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Validate delivery type
    if delivery_type not in ["subscription", "individual"]:
        raise HTTPException(status_code=400, detail="delivery_type must be 'subscription' or 'individual'")
    
    result = await vpn_service.create_multi_panel_config(order)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create VPN configs")
    
    if delivery_type == "subscription":
        return {
            "order_id": str(order.id),
            "delivery_type": "subscription",
            "subscription_url": result["subscription_url"],
            "total_configs": result["total_configs"]
        }
    else:
        return {
            "order_id": str(order.id),
            "delivery_type": "individual",
            "configs": result["individual_configs"],
            "total_configs": result["total_configs"]
        }
        


@router.get("/inbounds")
async def get_inbounds(panel_key: str, token: str = Depends(verify_token)):
    """Get all inbounds from specific 3x-ui panel"""
    from app.core.panel_config import panel_config
    
    panel_info = panel_config.get_panel(panel_key)
    if not panel_info:
        raise HTTPException(status_code=400, detail=f"Invalid panel key: {panel_key}")
    
    panel_service = XUIService(panel_key)
    inbounds = await panel_service.get_inbounds()
    if not inbounds:
        raise HTTPException(status_code=500, detail=f"Failed to get inbounds from {panel_info['name']} panel")
    return {"panel": panel_info['name'], "panel_key": panel_key, "inbounds": inbounds}

@router.get("/inbounds/all")
async def get_all_inbounds(token: str = Depends(verify_token)):
    """Get inbounds from all enabled panels"""
    from app.core.panel_config import panel_config
    
    enabled_panels = panel_config.get_enabled_panels()
    results = {}
    
    for panel_key, panel_info in enabled_panels.items():
        try:
            panel_service = XUIService(panel_key)
            inbounds = await panel_service.get_inbounds()
            results[panel_key] = {
                "name": panel_info['name'],
                "flag": panel_info['flag'],
                "inbounds": inbounds
            }
        except Exception as e:
            results[panel_key] = {"error": str(e)}
    return results

@router.post("/test-connection")
async def test_xui_connection(panel_key: str, token: str = Depends(verify_token)):
    """Test connection to 3x-ui panel"""
    from app.core.panel_config import panel_config
    
    panel_info = panel_config.get_panel(panel_key)
    if not panel_info:
        raise HTTPException(status_code=400, detail=f"Invalid panel key: {panel_key}")
    
    panel_service = XUIService(panel_key)
    success = await panel_service.login()
    if success:
        return {"status": "success", "message": f"Connected to {panel_info['name']} panel"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to connect to {panel_info['name']} panel")


@router.delete("/cancel/{order_id}")
async def cancel_vpn_config(order_id: str, token: str = Depends(verify_token)):
    """Cancel VPN configuration for an order (multi-panel)"""
    try:
        from bson import ObjectId
        if ObjectId.is_valid(order_id):
            order = await Order.get(ObjectId(order_id))
        else:
            order = await Order.find_one(Order.id == order_id)
    except:
        order = None
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    success = await vpn_service.delete_vpn_config(order)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel VPN configs")
    
    order.status = "cancelled"
    await order.save()
    
    return {"message": "VPN configs cancelled successfully from all panels"}

@router.get("/configs/{user_token}")
async def get_user_configs(user_token: str, token: str = Depends(verify_token)):
    """Get all config URLs for a user"""
    configs = await vpn_service.get_user_configs(user_token)
    if not configs:
        raise HTTPException(status_code=404, detail="No configs found for user")
    
    return {
        "configs": configs,
        "total_configs": len(configs)
    }

@router.get("/check/{order_id}")
async def check_user_info(order_id: str, token: str = Depends(verify_token)):
    """Check user info and configs by order ID (for support)"""
    try:
        from bson import ObjectId
        order = await Order.get(ObjectId(order_id)) if ObjectId.is_valid(order_id) else None
    except:
        order = None
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get user and plan info
    user = await order.user.fetch() if hasattr(order.user, 'fetch') else order.user
    plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
    
    # Get configs from order's panel_configs or user's subscriptions
    configs = []
    subscription_url = order.subscription_url
    
    if order.panel_configs:
        for sub_link in order.panel_configs:
            sub = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
            if sub and sub.subscription_token:
                from app.core.config import settings
                subscription_url = f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{sub.subscription_token}"
                configs = await vpn_service.get_user_configs(sub.subscription_token)
                break
    elif user and user.subscriptions:
        # Fallback: check user's subscriptions
        for sub_link in user.subscriptions:
            sub = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
            if sub and sub.is_active and sub.subscription_token:
                from app.core.config import settings
                subscription_url = f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{sub.subscription_token}"
                configs = await vpn_service.get_user_configs(sub.subscription_token)
                break
    
    return {
        "order_id": str(order.id),
        "user_id": user.telegram_id if user else None,
        "user_name": user.first_name if user else None,
        "plan_name": plan.name if plan else None,
        "protocol": order.protocol,
        "status": order.status,
        "created_at": order.created_at,
        "expires_at": order.expires_at,
        "subscription_url": subscription_url,
        "configs": configs,
        "total_configs": len(configs)
    }



@router.get("/panels/list")
async def list_panels(token: str = Depends(verify_token)):
    """List all configured panels from YAML"""
    from app.core.panel_config import panel_config
    
    all_panels = panel_config.load()['panels']
    return {
        "panels": [
            {
                "key": panel_key,
                "name": panel_info["name"],
                "direct_ip": panel_info["direct_ip"],
                "flag": panel_info["flag"],
                "enabled": panel_info.get("enabled", False),
                "max_users": panel_info.get("max_users", 0)
            } for panel_key, panel_info in all_panels.items()
        ]
    }

@router.get("/panels/status")
async def get_panels_status(token: str = Depends(verify_token)):
    """Get user count and status for all panels"""
    from app.core.panel_config import panel_config
    from app.services.load_balancer import load_balancer
    from app.models.subscription import Subscription
    
    await load_balancer.sync_server_loads()
    
    enabled_panels = panel_config.get_enabled_panels()
    panel_status = []
    
    for panel_key, panel_info in enabled_panels.items():
        # Count subscriptions on this panel
        subscriptions = await Subscription.find(Subscription.is_active == True).to_list()
        user_count = sum(1 for sub in subscriptions if any(
            config.panel_name.lower().replace(' ', '') == panel_info['name'].lower().replace(' ', '')
            for config in sub.configs
        ))
        
        max_users = panel_info.get('max_users', 50)
        usage_percent = (user_count / max_users * 100) if max_users > 0 else 0
        
        panel_status.append({
            "key": panel_key,
            "name": panel_info['name'],
            "flag": panel_info['flag'],
            "current_users": user_count,
            "max_users": max_users,
            "usage_percent": round(usage_percent, 1),
            "enabled": panel_info.get('enabled', True)
        })
    
    return {"panels": panel_status}

@router.post("/balance")
async def balance_servers(token: str = Depends(verify_token)):
    """Manually trigger auto-balance across all panels"""
    from app.services.migration_service import migration_service
    
    result = await migration_service.balance_servers()
    
    return {
        "message": "Auto-balance completed",
        "result": result
    }

@router.post("/evacuate/{source_panel_key}")
async def evacuate_panel(source_panel_key: str, target_panel_key: str = None, reset_traffic: bool = True, token: str = Depends(verify_token)):
    """Emergency: Evacuate ALL users from a filtered/blocked panel
    
    Args:
        source_panel_key: Panel to evacuate from
        target_panel_key: Panel to evacuate to (auto-select if not specified)
        reset_traffic: True = reset used traffic (give full traffic back)
                      False = preserve used traffic (subtract from total)
    """
    from app.core.panel_config import panel_config
    from app.services.migration_service import migration_service
    
    source_panel = panel_config.get_panel(source_panel_key)
    if not source_panel:
        raise HTTPException(status_code=404, detail=f"Source panel {source_panel_key} not found")
    
    # If no target specified, use least loaded panel
    if not target_panel_key:
        from app.services.load_balancer import load_balancer
        target_panel_key = await load_balancer.get_available_server()
    
    target_panel = panel_config.get_panel(target_panel_key)
    if not target_panel:
        raise HTTPException(status_code=404, detail=f"Target panel {target_panel_key} not found")
    
    # Migrate ALL users from source to target
    result = await migration_service.migrate_users_from_panel(
        source_panel['name'],
        target_panel_key,
        max_users=9999,  # No limit - evacuate all
        reset_traffic=reset_traffic
    )
    
    return {
        "message": f"Evacuation from {source_panel['name']} to {target_panel['name']} completed",
        "source_panel": source_panel['name'],
        "target_panel": target_panel['name'],
        "reset_traffic": reset_traffic,
        "result": result
    }



@router.get("/health")
def health_check():
    return {"status": "healthy"}