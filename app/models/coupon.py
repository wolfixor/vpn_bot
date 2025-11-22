from beanie import Document, Link
from pydantic import Field
from datetime import datetime
from enum import Enum
from typing import Optional, List
from app.models.user import User
from app.models.vpn_plan import VPNPlan

class DiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"

class CouponUsage(Document):
    coupon_code: str
    user: Link[User]
    vpn_plan: Link[VPNPlan]
    order_id: str
    discount_amount: float
    original_price: float
    final_price: float
    used_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "coupon_usages"

class Coupon(Document):
    code: str = Field(unique=True, index=True)
    discount_type: DiscountType
    discount_value: float  # percentage (0-100) or fixed amount
    max_uses: Optional[int] = None  # None = unlimited
    current_uses: int = 0
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None
    is_active: bool = True
    
    # Optional: restrict to specific plans
    allowed_plans: List[str] = []  # Empty = all plans allowed
    
    # Tracking
    total_discount_given: float = 0.0
    total_revenue: float = 0.0
    
    class Settings:
        name = "coupons"
    
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        now = datetime.utcnow()
        if now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True
    
    def calculate_discount(self, price: float) -> float:
        if self.discount_type == DiscountType.PERCENTAGE:
            return price * (self.discount_value / 100)
        return min(self.discount_value, price)
