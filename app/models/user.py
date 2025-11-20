from beanie import Document, Link
from pydantic import Field
from datetime import datetime
from typing import Optional, List
from app.models.subscription import Subscription

class User(Document):
    telegram_id: int = Field(unique=True)
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    
    # Multi-panel support
    subscription_token: Optional[str] = None  # Unique token for subscription URL
    subscriptions: List[Link[Subscription]] = []  # Each purchase = 1 subscription with multiple configs
    total_traffic_used: int = 0  # Aggregated traffic from all panels
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "users"