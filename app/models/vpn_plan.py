from beanie import Document
from pydantic import Field
from typing import Optional

class VPNPlan(Document):
    name: str
    duration_days: int
    price: float
    traffic_limit_gb: Optional[int] = None  # None = unlimited
    max_connections: int = 1
    is_active: bool = True
    description: Optional[str] = None
    
    class Settings:
        name = "vpn_plans"