from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import settings

class Database:
    client: AsyncIOMotorClient = None

db = Database()

async def connect_to_mongo():
    """Create database connection"""
    db.client = AsyncIOMotorClient(settings.MONGODB_URL)
    
async def close_mongo_connection():
    """Close database connection"""
    db.client.close()

async def init_db():
    """Initialize database with models"""
    from app.models.user import User
    from app.models.vpn_plan import VPNPlan
    from app.models.order import Order
    from app.models.payment import Payment
    from app.models.subscription import Subscription
    from app.models.server_load import ServerLoad
    from app.models.coupon import Coupon, CouponUsage
    
    await init_beanie(
        database=db.client[settings.DATABASE_NAME],
        document_models=[User, VPNPlan, Order, Payment, Subscription, ServerLoad, Coupon, CouponUsage]
    )
    
    
# Motor → async MongoDB client

# Beanie → ODM (Object Document Mapper) built on top of Motor