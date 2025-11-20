"""Test script for payment and subscription expiry"""
import asyncio
from datetime import datetime, timedelta
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.models.user import User
from app.models.order import Order
from app.models.vpn_plan import VPNPlan


async def setup_db():
    """Initialize database"""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[User, VPNPlan, Order, Payment, Subscription]
    )


async def test_payment_expiry():
    """Test 1: Create expired payment"""
    print("\n=== Test 1: Payment Expiry ===")
    
    # Find a user
    user = await User.find_one()
    if not user:
        print("❌ No users found. Create a user first.")
        return
    
    # Create test order
    plan = await VPNPlan.find_one()
    if not plan:
        print("❌ No plans found.")
        return
    
    from app.models.order import OrderStatus
    order = Order(
        user=user,
        vpn_plan=plan,
        protocol="v2ray",
        price=plan.price,
        status=OrderStatus.PAYMENT_PENDING
    )
    await order.save()
    
    # Create expired payment (1 minute ago)
    payment = Payment(
        order_id=str(order.id),
        user_telegram_id=user.telegram_id,
        payment_method="card_to_card",
        amount=plan.price,
        currency="USD",
        status="pending",
        expires_at=datetime.utcnow() - timedelta(minutes=1)  # Already expired
    )
    await payment.save()
    
    print(f"✅ Created expired payment: {payment.id}")
    print(f"   User: {user.telegram_id}")
    print(f"   Expired: {payment.expires_at}")
    print("\n💡 Run the bot and wait 5 minutes to see notification")


async def test_subscription_expiry():
    """Test 2: Create expired subscription"""
    print("\n=== Test 2: Subscription Expiry ===")
    
    user = await User.find_one()
    if not user:
        print("❌ No users found.")
        return
    
    # Create expired subscription
    from app.models.subscription import ConfigItem
    sub = Subscription(
        base_name="test_expired",
        user_telegram_id=user.telegram_id,
        configs=[
            ConfigItem(
                panel_name="Germany",
                inbound_id=1,
                client_uuid="test-uuid",
                client_email="test_expired_inbound1"
            )
        ],
        total_limit=10 * 1024**3,  # 10GB
        traffic_used=0,
        expires_at=datetime.utcnow() - timedelta(days=1),  # Expired yesterday
        is_active=True
    )
    await sub.save()
    
    print(f"✅ Created expired subscription: {sub.id}")
    print(f"   User: {user.telegram_id}")
    print(f"   Expired: {sub.expires_at}")
    print("\n💡 Run the bot and wait 1 hour to see notification")


async def test_traffic_warning():
    """Test 3: Create subscription with low traffic"""
    print("\n=== Test 3: Traffic Warning ===")
    
    user = await User.find_one()
    if not user:
        print("❌ No users found.")
        return
    
    # Create subscription with 0.5GB remaining
    from app.models.subscription import ConfigItem
    total_limit = 10 * 1024**3  # 10GB
    used = 9.5 * 1024**3  # 9.5GB used
    
    sub = Subscription(
        base_name="test_low_traffic",
        user_telegram_id=user.telegram_id,
        configs=[
            ConfigItem(
                panel_name="Germany",
                inbound_id=1,
                client_uuid="test-uuid-2",
                client_email="test_low_traffic_inbound1"
            )
        ],
        total_limit=int(total_limit),
        traffic_used=int(used),
        expires_at=datetime.utcnow() + timedelta(days=30),
        is_active=True,
        traffic_warned=False
    )
    await sub.save()
    
    print(f"✅ Created low-traffic subscription: {sub.id}")
    print(f"   User: {user.telegram_id}")
    print(f"   Remaining: 0.5GB")
    print("\n💡 Run the bot and wait 1 hour to see warning")


async def test_expiry_warning():
    """Test 4: Create subscription expiring in 3 days"""
    print("\n=== Test 4: Expiry Warning ===")
    
    user = await User.find_one()
    if not user:
        print("❌ No users found.")
        return
    
    from app.models.subscription import ConfigItem
    sub = Subscription(
        base_name="test_expiring_soon",
        user_telegram_id=user.telegram_id,
        configs=[
            ConfigItem(
                panel_name="Germany",
                inbound_id=1,
                client_uuid="test-uuid-3",
                client_email="test_expiring_soon_inbound1"
            )
        ],
        total_limit=10 * 1024**3,
        traffic_used=0,
        expires_at=datetime.utcnow() + timedelta(days=3),  # Expires in 3 days
        is_active=True,
        expiry_warned=False
    )
    await sub.save()
    
    print(f"✅ Created expiring subscription: {sub.id}")
    print(f"   User: {user.telegram_id}")
    print(f"   Expires in: 3 days")
    print("\n💡 Run the bot and wait 1 hour to see warning")


async def list_test_data():
    """List all test data"""
    print("\n=== Current Test Data ===")
    
    # Expired payments
    expired_payments = await Payment.find({
        "status": "pending",
        "expires_at": {"$lt": datetime.utcnow()}
    }).to_list()
    print(f"\n📋 Expired Payments: {len(expired_payments)}")
    for p in expired_payments:
        print(f"   - {p.id} | User: {p.user_telegram_id} | Expired: {p.expires_at}")
    
    # Test subscriptions
    test_subs = await Subscription.find({
        "base_name": {"$regex": "^test_"}
    }).to_list()
    print(f"\n📦 Test Subscriptions: {len(test_subs)}")
    for s in test_subs:
        print(f"   - {s.base_name} | Active: {s.is_active} | Expires: {s.expires_at}")


async def cleanup_test_data():
    """Remove all test data"""
    print("\n=== Cleaning Test Data ===")
    
    # Delete test subscriptions
    result = await Subscription.find({"base_name": {"$regex": "^test_"}}).delete()
    print(f"✅ Deleted {result.deleted_count} test subscriptions")
    
    # Delete expired test payments
    result = await Payment.find({
        "status": {"$in": ["pending", "expired"]},
        "expires_at": {"$lt": datetime.utcnow()}
    }).delete()
    print(f"✅ Deleted {result.deleted_count} expired payments")


async def main():
    await setup_db()
    
    print("\n" + "="*50)
    print("VPN Bot Expiry Testing")
    print("="*50)
    
    while True:
        print("\nOptions:")
        print("1. Test Payment Expiry (1 hour)")
        print("2. Test Subscription Expiry")
        print("3. Test Traffic Warning (<1GB)")
        print("4. Test Expiry Warning (3 days)")
        print("5. List Test Data")
        print("6. Cleanup Test Data")
        print("0. Exit")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "1":
            await test_payment_expiry()
        elif choice == "2":
            await test_subscription_expiry()
        elif choice == "3":
            await test_traffic_warning()
        elif choice == "4":
            await test_expiry_warning()
        elif choice == "5":
            await list_test_data()
        elif choice == "6":
            await cleanup_test_data()
        elif choice == "0":
            break
        else:
            print("❌ Invalid option")


if __name__ == "__main__":
    asyncio.run(main())
