from telegram import Update
from telegram.ext import ContextTypes
from app.core.config import settings

class ChannelVerification:
    """Handle channel verification for users"""
    
    def __init__(self, channel_username: str, channel_url: str):
        self.channel_username = channel_username
        self.channel_url = channel_url
    
    async def is_member(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        """Check if user is member of the required channel"""
        try:
            member = await context.bot.get_chat_member(self.channel_username, user_id)
            return member.status in ['member', 'administrator', 'creator']
        except Exception as e:
            print(f"Error checking channel membership: {e}")
            return False
    
    async def get_member_count(self, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get channel member count"""
        try:
            chat = await context.bot.get_chat(self.channel_username)
            return chat.member_count or 0
        except:
            return 0

# Default channel verification instance
channel_verifier = ChannelVerification(
    channel_username="@wolfixvpn",  # Replace with your channel
    channel_url="https://t.me/wolfixvpn"  # Replace with your channel URL
)