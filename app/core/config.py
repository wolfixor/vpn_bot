from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Dict, Any

class Settings(BaseSettings):
    PROJECT_NAME: str = "VPN Sell API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    
    # MongoDB
    MONGODB_URL: str
    DATABASE_NAME: str
    CARD_NUMBER: str
    NAME_CARD: str
    TETHER: str
    TRON: str
    SOLANA: str
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str
    
    # Telegram Channels
    NEWS_CHANNEL_USERNAME: str = "@vpn_news"
    NEWS_CHANNEL_URL: str = "https://t.me/vpn_news"
    PAYMENT_CHANNEL_ID: int = -1001234567890
    PAYMENT_CHANNEL_URL: str = "https://t.me/+your_private_channel_invite_link"
    
    # Bot Settings
    SUPPORT_USERNAME: str = "@support"
    BOT_ADMIN_IDS: str = "123456789,987654321"  # Comma-separated admin user IDs
    BOT_NAME: str = "VPN Bot"
    BOT_DESCRIPTION: str = ""
    BOT_SHORT_DESCRIPTION: str = ""
    
    # VPN Service Settings
    DEFAULT_SUBSCRIPTION_DOMAIN: str = "https://yourbot.com"
    ENABLE_PAYMENT_VERIFICATION: bool = False
    ENABLE_CHANNEL_VERIFICATION: bool = False
    
    # API Documentation Security
    DOCS_PATH: str = "/asdfasdfasfdf/docs"
    REDOC_PATH: str = "/asdfasdfasfdf/redoc"
    
    # API Security
    API_TOKEN: str = "your-secure-api-token-change-in-production"
    
    # Panel Credentials
    PANEL_USERNAME: str = "admin"
    PANEL_PASSWORD: str = "password"
    GERMANY_PANEL_USERNAME: str = "admin"
    GERMANY_PANEL_PASSWORD: str = "password"
    TURKEY_PANEL_USERNAME: str = "admin"
    TURKEY_PANEL_PASSWORD: str = "password"
    
    @field_validator('ENABLE_PAYMENT_VERIFICATION', 'ENABLE_CHANNEL_VERIFICATION', mode='before')
    @classmethod
    def parse_bool(cls, v: Any) -> bool:
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    class Config:
        env_file = ".env"

settings = Settings()