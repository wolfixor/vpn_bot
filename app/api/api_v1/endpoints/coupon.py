from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models.coupon import Coupon, CouponUsage, DiscountType
from app.models.vpn_plan import VPNPlan

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
async def create_coupon(data: CouponCreate):
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
async def list_coupons():
    """List all coupons"""
    coupons = await Coupon.find().to_list()
    return {"coupons": [c.dict() for c in coupons]}

@router.get("/coupons/{code}/stats")
async def get_coupon_stats(code: str):
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
async def update_coupon(code: str, is_active: Optional[bool] = None, max_uses: Optional[int] = None):
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
async def delete_coupon(code: str):
    """Delete coupon"""
    coupon = await Coupon.find_one(Coupon.code == code.upper())
    if not coupon:
        raise HTTPException(404, "Coupon not found")
    
    await coupon.delete()
    return {"success": True, "message": "Coupon deleted"}
