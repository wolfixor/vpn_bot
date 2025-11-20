from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import json
import httpx
from app.models.vpn_plan import VPNPlan
from app.models.order import Order
from app.services.vpn_service import vpn_service
from app.services.xui_service import XUIService



router = APIRouter()

@router.get("/plans", response_model=List[VPNPlan])
async def get_vpn_plans():
    """Get all active VPN plans"""
    plans = await VPNPlan.find(VPNPlan.is_active == True).to_list()
    return plans


@router.post("/plans/seed")
async def set_vpn_plans():
    sample_plans = [
        {
            "name": "Basic Plan",
            "duration_days": 30,
            "price": 9.99,
            "traffic_limit_gb": 100,
            "is_active": True
        },        
        {
            "name": "Premium Plan",
            "duration_days": 90,
            "price": 19.99,
            "traffic_limit_gb": 200,
            "is_active": True
        },
        {
            "name": "Enterprise Plan",
            "duration_days": 180,
            "price": 49.99,
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
async def create_vpn_config(order_id: str, delivery_type: str = "subscription"):
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
            "delivery_type": "subscription",
            "subscription_url": result["subscription_url"],
            "total_configs": result["total_configs"]
        }
    else:
        return {
            "delivery_type": "individual",
            "configs": result["individual_configs"],
            "total_configs": result["total_configs"]
        }
        


@router.get("/inbounds")
async def get_inbounds(panel_name: str = "germany"):
    """Get all inbounds from specific 3x-ui panel"""
    valid_panels = ["germany", "turkey"]
    if panel_name not in valid_panels:
        raise HTTPException(status_code=400, detail=f"Invalid panel. Must be one of: {valid_panels}")
    
    panel_service = XUIService(panel_name)
    inbounds = await panel_service.get_inbounds()
    if not inbounds:
        raise HTTPException(status_code=500, detail=f"Failed to get inbounds from {panel_name} panel")
    return {"panel": panel_name, "inbounds": inbounds}

@router.get("/inbounds/all")
async def get_all_inbounds():
    """Get inbounds from all panels"""
    results = {}
    for panel_name in ["germany", "turkey"]:
        try:
            panel_service = XUIService(panel_name)
            inbounds = await panel_service.get_inbounds()
            results[panel_name] = inbounds
        except Exception as e:
            results[panel_name] = {"error": str(e)}
    return results

@router.post("/test-connection")
async def test_xui_connection(panel_name: str = "germany"):
    """Test connection to 3x-ui panel"""
    panel_service = XUIService(panel_name)
    success = await panel_service.login()
    print(success, "result of login")
    if success:
        return {"status": "success", "message": f"Connected to {panel_name} panel"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to connect to {panel_name} panel")


@router.delete("/cancel/{order_id}")
async def cancel_vpn_config(order_id: str):
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
async def get_user_configs(user_token: str):
    """Get all config URLs for a user"""
    configs = await vpn_service.get_user_configs(user_token)
    if not configs:
        raise HTTPException(status_code=404, detail="No configs found for user")
    
    return {
        "configs": configs,
        "total_configs": len(configs)
    }



@router.get("/panels/list")
async def list_panels():
    """List all configured panels"""
    from app.services.vpn_service import vpn_service
    return {
        "panels": [
            {
                "name": panel_info["name"],
                "ip": panel_info["ip"],
                "flag": panel_info["flag"],
                "enabled": True
            } for panel_name, panel_info in vpn_service.ENABLED_PANELS.items()
        ]
    }



@router.get("/health")
def health_check():
    return {"status": "healthy"}