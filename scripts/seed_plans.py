#!/usr/bin/env python3
"""
Seed VPN plans based on pricing table
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import connect_to_mongo, init_db
from app.models.vpn_plan import VPNPlan

async def seed_plans():
    """Seed VPN plans from pricing table"""
    await connect_to_mongo()
    await init_db()
    
    # Clear existing plans
    await VPNPlan.delete_all()
    
    plans = [
        # 1 Month Plans
        {"name": "1 ماه - 10GB", "duration_days": 30, "price": 60000, "traffic_limit_gb": 10},
        {"name": "1 ماه - 20GB", "duration_days": 30, "price": 80000, "traffic_limit_gb": 20},
        {"name": "1 ماه - 30GB", "duration_days": 30, "price": 100000, "traffic_limit_gb": 30},
        {"name": "1 ماه - 50GB", "duration_days": 30, "price": 140000, "traffic_limit_gb": 50},
        {"name": "1 ماه - 75GB", "duration_days": 30, "price": 180000, "traffic_limit_gb": 75},
        {"name": "1 ماه - 100GB", "duration_days": 30, "price": 220000, "traffic_limit_gb": 100},
        {"name": "1 ماه - نامحدود", "duration_days": 30, "price": 420000, "traffic_limit_gb": None, "estimated_traffic_gb": 200},
        
        # 2 Month Plans
        {"name": "2 ماه - 30GB", "duration_days": 60, "price": 180000, "traffic_limit_gb": 30},
        {"name": "2 ماه - 50GB", "duration_days": 60, "price": 280000, "traffic_limit_gb": 50},
        {"name": "2 ماه - 75GB", "duration_days": 60, "price": 360000, "traffic_limit_gb": 75},
        {"name": "2 ماه - 100GB", "duration_days": 60, "price": 440000, "traffic_limit_gb": 100},
        {"name": "2 ماه - نامحدود", "duration_days": 60, "price": 750000, "traffic_limit_gb": None, "estimated_traffic_gb": 400},
        
        # 3 Month Plans
        {"name": "3 ماه - 75GB", "duration_days": 90, "price": 540000, "traffic_limit_gb": 75},
        {"name": "3 ماه - 100GB", "duration_days": 90, "price": 660000, "traffic_limit_gb": 100},
        {"name": "3 ماه - نامحدود", "duration_days": 90, "price": 1050000, "traffic_limit_gb": None, "estimated_traffic_gb": 800},
    ]
    
    for plan_data in plans:
        plan = VPNPlan(**plan_data)
        await plan.save()
        print(f"✅ Created: {plan.name} - {plan.price:,} تومان")
    
    print(f"\n🎉 Created {len(plans)} VPN plans successfully!")

if __name__ == "__main__":
    asyncio.run(seed_plans())