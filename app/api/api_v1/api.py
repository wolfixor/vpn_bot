from fastapi import APIRouter
from app.api.api_v1.endpoints import vpn, subscription

api_router = APIRouter()
api_router.include_router(vpn.router, prefix="/vpn", tags=["vpn"])
api_router.include_router(subscription.router, prefix="/subscription", tags=["subscription"])