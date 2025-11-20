"""Quick test - manually trigger expiry checks"""
import asyncio
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User
from app.models.order import Order
from app.models.vpn_plan import VPNPlan


class MockBot:
    """Mock bot for testing"""
    async def send_message(self, chat_id, text, parse_mode=None):
        print(f"\n📨 Message to {chat_id}:")
        print(text)
        print("-" * 50)


async def main():
    # Setup DB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[User, VPNPlan, Order, Payment, Subscription]
    )
    
    bot = MockBot()
    
    print("="*50)
    print("Running Expiry Checks NOW")
    print("="*50)
    
    # Import and run checks
    from app.services.payment_expiry_checker import check_expired_payments, check_expired_subscriptions
    
    print("\n🔍 Checking expired payments...")
    # Run once (not in loop)
    try:
        expired_payments = await Payment.find({
            "status": "pending",
            "expires_at": {"$lt": __import__('datetime').datetime.utcnow()}
        }).to_list()
        
        print(f"Found {len(expired_payments)} expired payments")
        
        for payment in expired_payments:
            payment.status = "expired"
            await payment.save()
            
            order = await Order.get(payment.order_id)
            from app.models.order import OrderStatus
            order.status = OrderStatus.CANCELLED
            await order.save()
            
            await bot.send_message(
                chat_id=payment.user_telegram_id,
                text="⏰ **زمان پرداخت به پایان رسید**\n\nمتأسفانه زمان ارسال رسید پرداخت به پایان رسید.\n\nبرای خرید مجدد از دکمه 🛒 خرید VPN استفاده کنید.",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n🔍 Checking expired subscriptions...")
    # Run subscription check
    try:
        from datetime import datetime
        subscriptions = await Subscription.find({"is_active": True}).to_list()
        print(f"Found {len(subscriptions)} active subscriptions")
        
        for sub in subscriptions:
            now = datetime.utcnow()
            
            # Check expiry
            if sub.expires_at and sub.expires_at < now:
                print(f"⏰ Subscription {sub.base_name} expired")
                sub.is_active = False
                await sub.save()
                
                user = await User.find_one({"subscriptions": sub.id})
                if user:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=f"⏰ **اشتراک منقضی شد**\n\nاشتراک {sub.base_name} به پایان رسید.\n\nبرای تمدید از دکمه 🛒 خرید VPN استفاده کنید.",
                        parse_mode="Markdown"
                    )
            
            # Check traffic
            if sub.total_limit and sub.total_limit > 0:
                if sub.traffic_used >= sub.total_limit:
                    print(f"📊 Subscription {sub.base_name} traffic exceeded")
                    sub.is_active = False
                    await sub.save()
                    
                    user = await User.find_one({"subscriptions": sub.id})
                    if user:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=f"📊 **ترافیک تمام شد**\n\nاشتراک {sub.base_name} ترافیک خود را مصرف کرد.\n\nبرای تمدید از دکمه 🛒 خرید VPN استفاده کنید.",
                            parse_mode="Markdown"
                        )
                
                # Check warnings
                remaining_gb = (sub.total_limit - sub.traffic_used) / (1024**3)
                if remaining_gb < 1 and not sub.traffic_warned:
                    print(f"⚠️ Subscription {sub.base_name} low traffic")
                    user = await User.find_one({"subscriptions": sub.id})
                    if user:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=f"⚠️ **هشدار ترافیک**\n\nاشتراک {sub.base_name}:\nترافیک باقیمانده: {remaining_gb:.2f}GB\n\nبرای تمدید از دکمه 🛒 خرید VPN استفاده کنید.",
                            parse_mode="Markdown"
                        )
                        sub.traffic_warned = True
                        await sub.save()
            
            # Check expiry warning
            if sub.expires_at:
                days_left = (sub.expires_at - now).days
                if days_left == 3 and not sub.expiry_warned:
                    print(f"⏰ Subscription {sub.base_name} expiring soon")
                    user = await User.find_one({"subscriptions": sub.id})
                    if user:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=f"⏰ **هشدار انقضا**\n\nاشتراک {sub.base_name}:\n3 روز تا پایان اشتراک\n\nبرای تمدید از دکمه 🛒 خرید VPN استفاده کنید.",
                            parse_mode="Markdown"
                        )
                        sub.expiry_warned = True
                        await sub.save()
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Check complete!")


if __name__ == "__main__":
    asyncio.run(main())
