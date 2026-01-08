from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.database.database import connect_to_mongo, close_mongo_connection, init_db
from app.bot.bot import bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    await init_db()
    
    # Start background services
    from app.services.subscription_cleanup import start_subscription_cleanup
    from app.services.load_balancer import start_load_balancer_sync
    from app.services.panel_health_monitor import start_panel_health_monitor
    
    await start_subscription_cleanup()
    await start_load_balancer_sync()
    await start_panel_health_monitor()
    
    # Start Telegram bot if token is provided
    if settings.TELEGRAM_BOT_TOKEN:
        asyncio.create_task(bot.start())
    
    yield
    
    # Shutdown
    if settings.TELEGRAM_BOT_TOKEN:
        await bot.stop()
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url=settings.DOCS_PATH,
    redoc_url=settings.REDOC_PATH
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy", "service": "vpn_bot"}