#!/usr/bin/env python3
"""
Coupon management script
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import connect_to_mongo, init_db
from app.models.coupon import Coupon, DiscountType, CouponUsage
from datetime import datetime, timedelta

async def main():
    await connect_to_mongo()
    await init_db()
    
    print("🎁 Coupon Management Tool")
    print("=" * 40)
    
    print("\n📋 Options:")
    print("1. Create new coupon")
    print("2. List all coupons")
    print("3. View coupon stats")
    print("4. Deactivate coupon")
    print("5. Delete coupon")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        # Create coupon
        code = input("Coupon code (e.g., SUMMER2024): ").strip().upper()
        
        print("\nDiscount type:")
        print("1. Percentage (e.g., 20%)")
        print("2. Fixed amount (e.g., 50000 Rial)")
        dtype = input("Choose (1-2): ").strip()
        
        discount_type = DiscountType.PERCENTAGE if dtype == "1" else DiscountType.FIXED
        discount_value = float(input(f"Discount value ({'percentage 0-100' if dtype == '1' else 'amount in Rial'}): "))
        
        max_uses_input = input("Max uses (leave empty for unlimited): ").strip()
        max_uses = int(max_uses_input) if max_uses_input else None
        
        days_valid = input("Valid for how many days (leave empty for no expiry): ").strip()
        valid_until = datetime.utcnow() + timedelta(days=int(days_valid)) if days_valid else None
        
        coupon = Coupon(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            max_uses=max_uses,
            valid_until=valid_until
        )
        await coupon.insert()
        
        print(f"\n✅ Coupon '{code}' created successfully!")
        print(f"   Type: {discount_type}")
        print(f"   Value: {discount_value}")
        print(f"   Max uses: {max_uses or 'Unlimited'}")
        print(f"   Valid until: {valid_until.strftime('%Y-%m-%d') if valid_until else 'No expiry'}")
    
    elif choice == "2":
        # List coupons
        coupons = await Coupon.find().to_list()
        
        if not coupons:
            print("\n❌ No coupons found")
        else:
            print(f"\n📋 Total coupons: {len(coupons)}\n")
            for c in coupons:
                status = "🟢 Active" if c.is_active else "🔴 Inactive"
                print(f"{status} {c.code}")
                print(f"   Type: {c.discount_type} | Value: {c.discount_value}")
                print(f"   Uses: {c.current_uses}/{c.max_uses or '∞'}")
                print(f"   Revenue: {int(c.total_revenue / 1000):,} T | Discount given: {int(c.total_discount_given / 1000):,} T")
                if c.valid_until:
                    print(f"   Expires: {c.valid_until.strftime('%Y-%m-%d')}")
                print()
    
    elif choice == "3":
        # View stats
        code = input("Coupon code: ").strip().upper()
        coupon = await Coupon.find_one(Coupon.code == code)
        
        if not coupon:
            print(f"\n❌ Coupon '{code}' not found")
        else:
            usages = await CouponUsage.find(CouponUsage.coupon_code == code).to_list()
            
            print(f"\n📊 Stats for '{code}':")
            print(f"   Status: {'Active' if coupon.is_active else 'Inactive'}")
            print(f"   Type: {coupon.discount_type} | Value: {coupon.discount_value}")
            print(f"   Total uses: {coupon.current_uses}/{coupon.max_uses or '∞'}")
            print(f"   Total revenue: {int(coupon.total_revenue / 1000):,} Toman")
            print(f"   Total discount: {int(coupon.total_discount_given / 1000):,} Toman")
            
            if usages:
                print(f"\n📋 Usage history ({len(usages)} orders):")
                for u in usages:
                    user = await u.user.fetch()
                    plan = await u.vpn_plan.fetch()
                    print(f"   • {user.first_name} (@{user.username or 'N/A'})")
                    print(f"     Plan: {plan.name}")
                    print(f"     Original: {int(u.original_price / 1000):,}T → Final: {int(u.final_price / 1000):,}T (Saved: {int(u.discount_amount / 1000):,}T)")
                    print(f"     Date: {u.used_at.strftime('%Y-%m-%d %H:%M')}")
                    print()
    
    elif choice == "4":
        # Deactivate
        code = input("Coupon code to deactivate: ").strip().upper()
        coupon = await Coupon.find_one(Coupon.code == code)
        
        if not coupon:
            print(f"\n❌ Coupon '{code}' not found")
        else:
            coupon.is_active = False
            await coupon.save()
            print(f"\n✅ Coupon '{code}' deactivated")
    
    elif choice == "5":
        # Delete
        code = input("Coupon code to delete: ").strip().upper()
        confirm = input(f"Are you sure you want to delete '{code}'? (yes/no): ").strip().lower()
        
        if confirm == "yes":
            coupon = await Coupon.find_one(Coupon.code == code)
            if not coupon:
                print(f"\n❌ Coupon '{code}' not found")
            else:
                await coupon.delete()
                print(f"\n✅ Coupon '{code}' deleted")
        else:
            print("\n❌ Deletion cancelled")

if __name__ == "__main__":
    asyncio.run(main())
