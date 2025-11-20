from beanie import Document
from datetime import datetime
from typing import Optional
from pydantic import Field

class Payment(Document):
    order_id: str
    user_telegram_id: int
    payment_method: str  # "card_to_card" or "crypto"
    amount: float
    currency: str = "USD"
    
    # Payment proof
    proof_photo_file_id: Optional[str] = None
    proof_message: Optional[str] = None
    
    # Payment details
    payment_address: Optional[str] = None  # Card number or crypto address
    transaction_id: Optional[str] = None
    
    # Status tracking
    status: str = "pending"  # pending, confirmed, rejected, expired
    admin_message_id: Optional[int] = None  # Message ID in payment channel
    confirmed_by: Optional[int] = None  # Admin telegram ID who confirmed
    confirmed_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    class Settings:
        name = "payments"