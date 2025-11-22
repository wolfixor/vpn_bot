from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.models.user import User
from app.models.subscription import Subscription
from app.services.xui_service import XUIService
from app.core.panel_config import panel_config

class TrafficService:
    
    async def sync_user_traffic(self, user_id: int) -> Dict[str, int]:
        """Sync traffic usage from ALL panels and aggregate for user - estimate all configs together"""
        user = await User.find_one(User.telegram_id == user_id)
        if not user or not user.subscriptions:
            return {"total_used": 0, "panels_synced": 0}
        
        total_traffic_all_subscriptions = 0
        panels_synced = 0
        
        for sub_link in user.subscriptions:
            subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
            if not subscription or not subscription.is_active:
                continue
            
            # Aggregate traffic from ALL configs in this subscription
            subscription_traffic = 0
            for config_item in subscription.configs:
                try:
                    # Find panel dynamically by name
                    panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
                    if not panel_key:
                        continue
                    
                    panel_service = XUIService(panel_key)
                    client_stats = await panel_service.get_client_stats(
                        config_item.inbound_id, 
                        config_item.client_email
                    )
                    
                    if client_stats:
                        config_traffic = client_stats.get("down", 0) + client_stats.get("up", 0)
                        subscription_traffic += config_traffic
                        panels_synced += 1
                        print(f"📊 {config_item.panel_name} inbound {config_item.inbound_id}: {config_traffic / (1024**3):.2f}GB")
                        
                except Exception as e:
                    print(f"❌ Error syncing traffic for {config_item.panel_name}: {e}")
            
            # Update subscription traffic
            subscription.traffic_used = subscription_traffic
            await subscription.save()
            
            # Add to total (all subscriptions aggregated)
            total_traffic_all_subscriptions += subscription_traffic
        
        # Update user total traffic (aggregated from all subscriptions)
        user.total_traffic_used = total_traffic_all_subscriptions
        await user.save()
        
        print(f"📈 User {user_id} total traffic: {total_traffic_all_subscriptions / (1024**3):.2f}GB")
        
        return {
            "total_used": total_traffic_all_subscriptions,
            "panels_synced": panels_synced,
            "total_subscriptions": len(user.subscriptions)
        }
    
    async def get_user_traffic_summary(self, user_id: int) -> Dict:
        """Get comprehensive traffic summary - aggregate ALL configs but estimate based on plan limits"""
        user = await User.find_one(User.telegram_id == user_id)
        if not user:
            return None
        
        # Sync latest traffic from ALL panels first
        sync_result = await self.sync_user_traffic(user_id)
        
        # Calculate aggregated totals from all subscriptions
        total_used_bytes = user.total_traffic_used or 0
        total_used_gb = total_used_bytes / (1024**3)
        
        # Aggregate limits from ALL active subscriptions
        total_estimated_limit_bytes = 0
        latest_expires_at = None
        active_subs = 0
        
        for sub_link in user.subscriptions:
            subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
            if subscription and subscription.is_active:
                # Add estimated limit (200GB for unlimited, actual for limited)
                total_estimated_limit_bytes += subscription.total_limit or 0
                
                # Use latest expiry date
                if subscription.expires_at:
                    if not latest_expires_at or subscription.expires_at > latest_expires_at:
                        latest_expires_at = subscription.expires_at
                
                active_subs += 1
        
        # Check if user has unlimited plans by checking original plan
        is_unlimited = False
        for sub_link in user.subscriptions:
            subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
            if subscription and subscription.is_active:
                # Find the original order to check if plan was unlimited
                from app.models.order import Order
                order = await Order.find_one({"panel_configs": subscription.id})
                if order:
                    plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
                    if plan and plan.traffic_limit_gb is None:
                        is_unlimited = True
                        break
        
        if is_unlimited:
            total_limit_gb = None  # Show as unlimited
            remaining_gb = None
            usage_percent = 0
        else:
            total_limit_gb = total_estimated_limit_bytes / (1024**3) if total_estimated_limit_bytes else 0
            remaining_gb = max(0, total_limit_gb - total_used_gb) if total_limit_gb else 0
            usage_percent = round((total_used_gb / total_limit_gb) * 100, 1) if total_limit_gb else 0
        
        # Calculate days remaining
        days_remaining = 0
        if latest_expires_at:
            days_remaining = max(0, (latest_expires_at - datetime.utcnow()).days)
        
        return {
            "total_used_gb": round(total_used_gb, 2),
            "total_limit_gb": total_limit_gb,
            "remaining_gb": round(remaining_gb, 2) if remaining_gb is not None else None,
            "usage_percent": usage_percent,
            "days_remaining": days_remaining,
            "expires_at": latest_expires_at,
            "active_subscriptions": active_subs,
            "is_unlimited": is_unlimited,
            "sync_result": sync_result
        }
    
    async def check_usage_alerts(self, user_id: int) -> List[str]:
        """Check if user needs usage alerts"""
        summary = await self.get_user_traffic_summary(user_id)
        if not summary:
            return []
        
        alerts = []
        
        # Traffic alerts
        if summary["remaining_gb"] is not None:
            if summary["remaining_gb"] <= 1.0:  # Less than 1GB
                alerts.append("traffic_low")
            elif summary["usage_percent"] >= 80:  # 80% used
                alerts.append("traffic_warning")
        
        # Expiry alerts
        if summary["days_remaining"] <= 3:  # 3 days or less
            alerts.append("expiry_warning")
        elif summary["days_remaining"] <= 1:  # 1 day or less
            alerts.append("expiry_critical")
        
        return alerts
    

    
    async def get_user_subscriptions_by_order(self, user_id: int) -> List[Dict]:
        """Get user subscriptions - each subscription aggregates ALL its configs"""
        from app.models.user import User
        from app.models.order import Order
        
        user = await User.find_one(User.telegram_id == user_id)
        if not user:
            return []
        
        # Get all paid orders
        orders = await Order.find(Order.user.id == user.id, Order.status == "paid").sort(-Order.created_at).to_list()
        
        subscriptions = []
        for order in orders:
            # Get subscription for this order
            if not order.panel_configs:
                continue
            
            subscription = await order.panel_configs[0].fetch() if hasattr(order.panel_configs[0], 'fetch') else order.panel_configs[0]
            if not subscription or not subscription.is_active:
                continue
            
            # Aggregate traffic from ALL configs in this subscription
            total_used = 0
            panels_used = set()
            
            for config_item in subscription.configs:
                try:
                    # Find panel dynamically by name
                    panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
                    if not panel_key:
                        continue
                    
                    panel_service = XUIService(panel_key)
                    stats = await panel_service.get_client_stats(config_item.inbound_id, config_item.client_email)
                    if stats:
                        config_traffic = stats.get("down", 0) + stats.get("up", 0)
                        total_used += config_traffic
                        panels_used.add(config_item.panel_name)
                        
                except Exception as e:
                    print(f"❌ Error syncing {config_item.panel_name}: {e}")
            
            subscription.traffic_used = total_used
            await subscription.save()
            
            plan = await order.vpn_plan.fetch()
            
            # Handle unlimited vs limited plans - show unlimited to user if plan is unlimited
            if plan.traffic_limit_gb is None:
                # Unlimited plan - show unlimited to user
                used_gb = total_used / (1024**3)
                limit_gb = None
                remaining_gb = None
                usage_percent = 0
                is_unlimited = True
            else:
                # Limited plan - show actual limits
                total_limit = plan.traffic_limit_gb * (1024**3)
                used_gb = total_used / (1024**3)
                limit_gb = total_limit / (1024**3)
                remaining_gb = max(0, limit_gb - used_gb)
                usage_percent = round((used_gb / limit_gb) * 100, 1) if limit_gb else 0
                is_unlimited = False
            
            days_remaining = max(0, (order.expires_at - datetime.utcnow()).days) if order.expires_at else 0
            
            subscriptions.append({
                "order_id": str(order.id),
                "plan_name": plan.name,
                "config_count": len(subscription.configs),
                "panels_count": len(panels_used),
                "panels_list": list(panels_used),
                "used_gb": round(used_gb, 2),
                "limit_gb": limit_gb,
                "remaining_gb": round(remaining_gb, 2) if remaining_gb is not None else None,
                "usage_percent": usage_percent,
                "is_unlimited": is_unlimited,
                "days_remaining": days_remaining,
                "expires_at": order.expires_at,
                "created_at": order.created_at
            })
        
        return subscriptions
    
    async def send_traffic_warning(self, context, user_id: int, remaining_gb: float):
        """Send traffic warning to user"""
        text = f"⚠️ **هشدار ترافیک**\n\n"
        text += f"📊 ترافیک باقیمانده: {remaining_gb:.2f}GB\n"
        text += f"💡 برای تمدید اشتراک از گزینه 'اشتراکهای من' استفاده کنید\n\n"
        text += f"🔄 برای مشاهده جزئیات بیشتر از گزینه زیر استفاده کنید"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown"
        )
    
    async def send_expiry_warning(self, context, user_id: int, days_remaining: int):
        """Send expiry warning to user"""
        text = f"⏰ **هشدار انقضا**\n\n"
        text += f"📅 روزهای باقیمانده: {days_remaining}\n"
        text += f"🔄 برای تمدید اشتراک اقدام کنید\n\n"
        text += f"💡 از گزینه 'اشتراکهای من' برای مشاهده جزئیات استفاده کنید"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown"
        )

traffic_service = TrafficService()