from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models.coupon import Coupon, CouponUsage, DiscountType
from app.models.vpn_plan import VPNPlan
from app.core.security import verify_token

router = APIRouter()

class CouponCreate(BaseModel):
    code: str
    discount_type: DiscountType
    discount_value: float
    max_uses: Optional[int] = None
    valid_until: Optional[datetime] = None
    allowed_plans: List[str] = []

class CouponStats(BaseModel):
    code: str
    discount_type: str
    discount_value: float
    current_uses: int
    max_uses: Optional[int]
    total_discount_given: float
    total_revenue: float
    is_active: bool
    valid_until: Optional[datetime]
    usage_details: List[dict]

@router.post("/coupons")
async def create_coupon(data: CouponCreate, token: str = Depends(verify_token)):
    """Create new coupon"""
    existing = await Coupon.find_one(Coupon.code == data.code)
    if existing:
        raise HTTPException(400, "Coupon code already exists")
    
    coupon = Coupon(
        code=data.code.upper(),
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        max_uses=data.max_uses,
        valid_until=data.valid_until,
        allowed_plans=data.allowed_plans
    )
    await coupon.insert()
    
    return {"success": True, "coupon": coupon.dict()}

@router.get("/coupons")
async def list_coupons(token: str = Depends(verify_token)):
    """List all coupons"""
    coupons = await Coupon.find().to_list()
    return {"coupons": [c.dict() for c in coupons]}

@router.get("/coupons/{code}/stats")
async def get_coupon_stats(code: str, token: str = Depends(verify_token)):
    """Get detailed coupon statistics"""
    coupon = await Coupon.find_one(Coupon.code == code.upper())
    if not coupon:
        raise HTTPException(404, "Coupon not found")
    
    usages = await CouponUsage.find(CouponUsage.coupon_code == code.upper()).to_list()
    
    usage_details = []
    for usage in usages:
        user = await usage.user.fetch()
        plan = await usage.vpn_plan.fetch()
        usage_details.append({
            "user_id": user.telegram_id,
            "username": user.username,
            "plan_name": plan.name,
            "order_id": usage.order_id,
            "original_price": usage.original_price,
            "discount_amount": usage.discount_amount,
            "final_price": usage.final_price,
            "used_at": usage.used_at.isoformat()
        })
    
    return CouponStats(
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        current_uses=coupon.current_uses,
        max_uses=coupon.max_uses,
        total_discount_given=coupon.total_discount_given,
        total_revenue=coupon.total_revenue,
        is_active=coupon.is_active,
        valid_until=coupon.valid_until,
        usage_details=usage_details
    )

@router.patch("/coupons/{code}")
async def update_coupon(code: str, is_active: Optional[bool] = None, max_uses: Optional[int] = None, token: str = Depends(verify_token)):
    """Update coupon settings"""
    coupon = await Coupon.find_one(Coupon.code == code.upper())
    if not coupon:
        raise HTTPException(404, "Coupon not found")
    
    if is_active is not None:
        coupon.is_active = is_active
    if max_uses is not None:
        coupon.max_uses = max_uses
    
    await coupon.save()
    return {"success": True, "coupon": coupon.dict()}

@router.delete("/coupons/{code}")
async def delete_coupon(code: str, token: str = Depends(verify_token)):
    """Delete coupon"""
    coupon = await Coupon.find_one(Coupon.code == code.upper())
    if not coupon:
        raise HTTPException(404, "Coupon not found")
    
    await coupon.delete()
    return {"success": True, "message": "Coupon deleted"}

@router.post("/restore-all-users")
async def restore_all_users(preserve_traffic: bool = False, token: str = Depends(verify_token)):
    """Disaster recovery: Restore all active users to current panels
    
    Args:
        preserve_traffic: If True, keeps current traffic usage and adjusts limits.
                         If False, resets traffic to 0 (fresh start).
    """
    from app.models.subscription import Subscription, ConfigItem
    from app.models.user import User
    from app.services.xui_service import XUIService
    from app.core.panel_config import panel_config
    from app.services.inbound_balancer import inbound_balancer
    import uuid
    
    subscriptions = await Subscription.find({"is_active": True}).to_list()
    enabled_panels = panel_config.get_enabled_panels()
    
    success_count = 0
    failed_count = 0
    
    for sub in subscriptions:
        try:
            user = await User.find_one({"subscriptions": sub.id})
            if not user:
                failed_count += 1
                continue
            
            # Calculate remaining traffic if preserving
            remaining_traffic = sub.total_limit
            if preserve_traffic and sub.traffic_used > 0:
                remaining_traffic = max(0, sub.total_limit - sub.traffic_used)
            
            sub.configs = []
            new_configs = []
            
            for panel_key, panel_info in enabled_panels.items():
                try:
                    panel_service = XUIService(panel_key)
                    inbound_assignments = await inbound_balancer.get_balanced_inbounds(panel_key)
                    
                    for inbound_id in inbound_assignments:
                        client_uuid = str(uuid.uuid4())
                        client_email = f"{sub.base_name}_{panel_key}_inbound{inbound_id}"
                        
                        result = await panel_service.add_client(
                            inbound_id=inbound_id,
                            email=client_email,
                            uuid=client_uuid,
                            total_gb=remaining_traffic,
                            expire_time=int(sub.expires_at.timestamp() * 1000) if sub.expires_at else 0
                        )
                        
                        if result:
                            new_configs.append(ConfigItem(
                                panel_name=panel_info['name'],
                                inbound_id=inbound_id,
                                client_uuid=client_uuid,
                                client_email=client_email
                            ))
                except:
                    pass
            
            if new_configs:
                sub.configs = new_configs
                if preserve_traffic:
                    # Keep current usage, update limit to remaining
                    sub.total_limit = remaining_traffic
                else:
                    # Reset traffic
                    sub.traffic_used = 0
                await sub.save()
                success_count += 1
            else:
                failed_count += 1
        except:
            failed_count += 1
    
    return {
        "success": True,
        "total_subscriptions": len(subscriptions),
        "restored": success_count,
        "failed": failed_count,
        "panels_used": len(enabled_panels),
        "traffic_preserved": preserve_traffic
    }
