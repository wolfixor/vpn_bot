from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional

class ServerLoad(Document):
    """Track subscription count per server for load balancing"""
    
    # Server identity
    panel_name: str  # "germany", "turkey"
    
    # Load tracking (subscriptions, not inbounds)
    current_subscriptions: int = 0
    max_subscriptions: int = 50  # Default limit
    
    # Status
    is_active: bool = True
    is_full: bool = False
    alert_sent: bool = False
    
    # Metadata
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "server_loads"
        
    def can_accept_subscription(self) -> bool:
        """Check if server can accept new subscription"""
        return self.is_active and self.current_subscriptions < self.max_subscriptions
    
    def increment_subscriptions(self):
        """Add a subscription to this server"""
        self.current_subscriptions += 1
        self.is_full = self.current_subscriptions >= self.max_subscriptions
        self.last_updated = datetime.utcnow()
        
    def decrement_subscriptions(self):
        """Remove a subscription from this server"""
        self.current_subscriptions = max(0, self.current_subscriptions - 1)
        self.is_full = False
        self.alert_sent = False
        self.last_updated = datetime.utcnow()
