from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional

class PanelConfig(Document):
    """Configuration for a client in a specific panel/inbound"""
    
    # Panel identification
    panel_name: str  # "germany", "turkey", etc.
    inbound_id: int  # 3x-ui inbound ID
    
    # Client details
    client_uuid: str  # VLESS/VMess UUID
    client_email: str  # Unique client identifier
    client_password: Optional[str] = None  # For Trojan protocol
    
    # 3x-ui specific
    sub_id: Optional[str] = None  # 3x-ui subscription ID
    xui_client_id: Optional[int] = None  # 3x-ui internal client ID
    
    # Traffic and limits
    traffic_used: int = 0  # Bytes used
    total_limit: int = 0  # Total bytes allowed (0 = unlimited)
    expires_at: Optional[datetime] = None
    
    # Status
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_online: Optional[datetime] = None
    
    class Settings:
        name = "panel_configs"