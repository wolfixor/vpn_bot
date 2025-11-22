"""Cleanup expired and traffic-exceeded subscriptions"""
import asyncio
from datetime import datetime
from app.models.subscription import Subscription
from app.services.load_balancer import load_balancer
from app.services.xui_service import XUIService
from app.core.panel_config import panel_config

async def cleanup_expired_subscriptions():
    """Remove expired subscriptions from ALL panels and deallocate properly"""
    while True:
        try:
            print(f"🧹 [{datetime.now()}] Cleaning expired subscriptions...")
            
            # Find expired subscriptions
            now = datetime.utcnow()
            expired_subs = await Subscription.find(
                Subscription.is_active == True,
                Subscription.expires_at < now
            ).to_list()
            
            for sub in expired_subs:
                print(f"🗑️ Removing expired subscription: {sub.base_name} (User: {sub.user_telegram_id})")
                
                # Delete subscription using VPN service
                from app.services.vpn_service import vpn_service
                await vpn_service.delete_subscription(sub)
                
                print(f"  ✅ Subscription {sub.base_name} fully cleaned up")
            
            if expired_subs:
                print(f"✅ Cleaned {len(expired_subs)} expired subscriptions")
            else:
                print("ℹ️ No expired subscriptions found")
            
        except Exception as e:
            print(f"❌ Error in cleanup: {e}")
        
        # Run every hour
        await asyncio.sleep(3600)

async def cleanup_traffic_exceeded_subscriptions():
    """Remove subscriptions that exceeded traffic limit"""
    from app.services.traffic_service import traffic_service
    
    while True:
        try:
            print(f"📊 [{datetime.now()}] Checking traffic limits...")
            
            # Find active subscriptions with limits
            active_subs = await Subscription.find(
                Subscription.is_active == True,
                Subscription.total_limit > 0  # Only limited plans
            ).to_list()
            
            for sub in active_subs:
                try:
                    # Sync traffic for this subscription
                    total_used = 0
                    for config in sub.configs:
                        try:
                            # Find panel dynamically by name
                            panel_key, panel_info = panel_config.get_panel_by_name(config.panel_name)
                            if not panel_key:
                                continue
                            
                            panel_service = XUIService(panel_key)
                            stats = await panel_service.get_client_stats(config.inbound_id, config.client_email)
                            if stats:
                                total_used += stats.get("down", 0) + stats.get("up", 0)
                        except Exception as e:
                            print(f"❌ Error checking config {config.client_email}: {e}")
                    
                    # Check if exceeded limit
                    if total_used >= sub.total_limit:
                        print(f"🚫 Subscription {sub.base_name} exceeded traffic limit")
                        
                        # Delete subscription
                        from app.services.vpn_service import vpn_service
                        await vpn_service.delete_subscription(sub)
                        print(f"  ✅ Subscription {sub.base_name} disabled for traffic limit")
                        
                except Exception as e:
                    print(f"❌ Error checking traffic for {sub.base_name}: {e}")
            
        except Exception as e:
            print(f"❌ Error in traffic cleanup: {e}")
        
        # Check every 30 minutes
        await asyncio.sleep(1800)

async def start_subscription_cleanup():
    """Start all subscription cleanup background tasks"""
    asyncio.create_task(cleanup_expired_subscriptions())
    asyncio.create_task(cleanup_traffic_exceeded_subscriptions())
    print("✅ Subscription cleanup tasks started")
