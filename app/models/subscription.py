from beanie import Document
from pydantic import Field, BaseModel
from datetime import datetime
from typing import List, Optional

class ConfigItem(BaseModel):
    """Single config within a subscription"""
    panel_name: str  # "Germany", "Turkey"
    inbound_id: int
    client_uuid: str
    client_email: str  # "Kobra_c7135768_inbound1"
    client_password: Optional[str] = None  # For Trojan protocol
    
class Subscription(Document):
    """One subscription = multiple configs across panels/inbounds"""
    
    # Subscription identity
    base_name: str  # "Kobra_c7135768" - user-friendly name
    user_telegram_id: int
    
    # All configs for this subscription
    configs: List[ConfigItem] = []
    
    # Shared limits (applies to ALL configs combined)
    total_limit: int = 0  # Total bytes allowed
    traffic_used: int = 0  # Total bytes used across all configs
    expires_at: Optional[datetime] = None
    
    # Status
    is_active: bool = True
    traffic_warned: bool = False  # Warning sent for low traffic
    expiry_warned: bool = False  # Warning sent for expiry
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "subscriptions"
