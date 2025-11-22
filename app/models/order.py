from beanie import Document, Link
from pydantic import Field
from datetime import datetime
from enum import Enum
from typing import Optional, List
from app.models.user import User
from app.models.vpn_plan import VPNPlan
from app.models.subscription import Subscription

class OrderStatus(str, Enum):
    PENDING = "pending"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class Order(Document):
    user: Link[User]
    vpn_plan: Link[VPNPlan]
    status: OrderStatus = OrderStatus.PENDING
    price: float
    original_price: Optional[float] = None
    coupon_code: Optional[str] = None
    discount_amount: Optional[float] = None
    
    # Multi-panel support
    protocol: str = "vless"  # "vless", "vmess", "trojan", "wireguard"
    panel_configs: List[Link[Subscription]] = []  # List of Subscription links
    subscription_url: Optional[str] = None  # Unified subscription URL
    
    # Legacy fields (for backward compatibility)
    xui_user_id: Optional[str] = None
    inbound_id: Optional[int] = None
    config_data: Optional[str] = None
    
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "orders"