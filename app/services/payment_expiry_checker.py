import asyncio
from datetime import datetime, timedelta
from app.models.payment import Payment
from app.models.order import Order, OrderStatus
from app.models.subscription import Subscription
from app.models.user import User
from app.services.xui_service import XUIService


async def check_expired_payments(bot):
    """Check for expired payments and notify users"""
    while True:
        try:
            # Find expired pending payments
            expired_payments = await Payment.find({
                "status": "pending",
                "expires_at": {"$lt": datetime.utcnow()}
            }).to_list()
            
            for payment in expired_payments:
                payment.status = "expired"
                await payment.save()
                
                order = await Order.get(payment.order_id)
                order.status = OrderStatus.CANCELLED
                await order.save()
                
                text = "⏰ **زمان پرداخت به پایان رسید**\n\n"
                text += "متأسفانه زمان ارسال رسید پرداخت به پایان رسید.\n\n"
                text += "برای خرید مجدد از گزینه 🛒 خرید VPN استفاده کنید."
                
                await bot.send_message(
                    chat_id=payment.user_telegram_id,
                    text=text,
                    parse_mode="Markdown"
                )
            
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"❌ Error checking expired payments: {e}")
            await asyncio.sleep(300)


async def check_expired_subscriptions(bot):
    """Check for expired or traffic-exceeded subscriptions"""
    while True:
        try:
            now = datetime.utcnow()
            
            # Find active subscriptions
            subscriptions = await Subscription.find({"is_active": True}).to_list()
            
            for sub in subscriptions:
                # Check expiry date
                if sub.expires_at and sub.expires_at < now:
                    await disable_subscription(bot, sub, "expired")
                    continue
                
                # Check traffic limit
                if sub.total_limit and sub.total_limit > 0:
                    # Sync traffic from panels
                    total_used = 0
                    for config_item in sub.configs:
                        try:
                            from app.core.panel_config import panel_config
                            panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
                            if not panel_key:
                                continue
                            
                            panel_service = XUIService(panel_key)
                            stats = await panel_service.get_client_stats(config_item.inbound_id, config_item.client_email)
                            if stats:
                                total_used += stats.get("down", 0) + stats.get("up", 0)
                        except Exception as e:
                            print(f"❌ Error syncing traffic for {config_item.client_email}: {e}")
                    
                    sub.traffic_used = total_used
                    await sub.save()
                    
                    # Check if exceeded
                    if total_used >= sub.total_limit:
                        await disable_subscription(bot, sub, "traffic_exceeded")
                        continue
                    
                    # Warn if close to limit (only for limited plans)
                    # Check if plan is unlimited by checking original order
                    from app.models.order import Order
                    order = await Order.find_one({"panel_configs": sub.id})
                    is_unlimited = False
                    if order:
                        plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
                        if plan and plan.traffic_limit_gb is None:
                            is_unlimited = True
                    
                    # Only warn about traffic for limited plans
                    if not is_unlimited:
                        remaining_gb = (sub.total_limit - total_used) / (1024**3)
                        if remaining_gb < 1 and not sub.traffic_warned:
                            user = await User.find_one({"subscriptions": sub.id})
                            if user:
                                text = f"⚠️ **هشدار ترافیک**\n\n"
                                text += f"اشتراک {sub.base_name}:\n"
                                text += f"ترافیک باقیمانده: {remaining_gb:.2f}GB\n\n"
                                text += "برای تمدید از گزینه 🛒 خرید VPN استفاده کنید."
                                
                                await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
                                sub.traffic_warned = True
                                await sub.save()
                
                # Warn 3 days before expiry
                if sub.expires_at:
                    days_left = (sub.expires_at - now).days
                    if days_left == 3 and not sub.expiry_warned:
                        user = await User.find_one({"subscriptions": sub.id})
                        if user:
                            text = f"⏰ **هشدار انقضا**\n\n"
                            text += f"اشتراک {sub.base_name}:\n"
                            text += f"3 روز تا پایان اشتراک\n\n"
                            text += "برای تمدید از گزینه 🛒 خرید VPN استفاده کنید."
                            
                            await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
                            sub.expiry_warned = True
                            await sub.save()
            
            # Check every hour
            await asyncio.sleep(3600)
            
        except Exception as e:
            print(f"❌ Error checking subscriptions: {e}")
            await asyncio.sleep(3600)


async def disable_subscription(bot, subscription: Subscription, reason: str):
    """Disable subscription and notify user"""
    subscription.is_active = False
    await subscription.save()
    
    # Disable all configs in panels
    for config_item in subscription.configs:
        try:
            from app.core.panel_config import panel_config
            panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
            if not panel_key:
                continue
            
            panel_service = XUIService(panel_key)
            await panel_service.delete_client(config_item.inbound_id, config_item.client_uuid)
        except Exception as e:
            print(f"❌ Error deleting config {config_item.client_email}: {e}")
    
    # Notify user
    user = await User.find_one({"subscriptions": subscription.id})
    if user:
        if reason == "expired":
            text = f"⏰ **اشتراک منقضی شد**\n\n"
            text += f"اشتراک {subscription.base_name} به پایان رسید.\n\n"
        else:
            text = f"📊 **ترافیک تمام شد**\n\n"
            text += f"اشتراک {subscription.base_name} ترافیک خود را مصرف کرد.\n\n"
        
        text += "برای تمدید از گزینه 🛒 خرید VPN استفاده کنید."
        
        await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
