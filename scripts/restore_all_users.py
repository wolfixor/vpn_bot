#!/usr/bin/env python3
"""
Disaster Recovery: Restore all active users to new servers
Use this when you lose all servers and need to recreate users on new infrastructure
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import connect_to_mongo, init_db
from app.models.subscription import Subscription, ConfigItem
from app.models.user import User
from app.services.xui_service import XUIService
from app.core.panel_config import panel_config
from app.services.inbound_balancer import inbound_balancer
import uuid

async def restore_all_users():
    """Recreate all active users on new servers"""
    await connect_to_mongo()
    await init_db()
    
    print("🔄 VPN Disaster Recovery Tool")
    print("=" * 50)
    print("⚠️  WARNING: This will recreate ALL active users on current panels")
    print("=" * 50)
    
    # Get all active subscriptions
    subscriptions = await Subscription.find({"is_active": True}).to_list()
    
    if not subscriptions:
        print("\n❌ No active subscriptions found")
        return
    
    print(f"\n📊 Found {len(subscriptions)} active subscriptions")
    
    # Show current panels
    enabled_panels = panel_config.get_enabled_panels()
    print(f"\n🌍 Current panels ({len(enabled_panels)}):")
    for key, info in enabled_panels.items():
        print(f"  • {info['name']} ({info['flag']}) - {key}")
    
    preserve = input("\n💾 Preserve current traffic usage? (yes/no): ").strip().lower()
    preserve_traffic = preserve == "yes"
    
    if preserve_traffic:
        print("✅ Traffic will be preserved (users keep their usage)")
    else:
        print("🔄 Traffic will be reset (users get fresh start)")
    
    confirm = input(f"\n⚠️  Recreate {len(subscriptions)} users on these panels? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("\n❌ Operation cancelled")
        return
    
    print("\n🚀 Starting restoration...\n")
    
    success_count = 0
    failed_count = 0
    
    for i, sub in enumerate(subscriptions, 1):
        try:
            print(f"[{i}/{len(subscriptions)}] Processing {sub.base_name}...")
            
            # Get user
            user = await User.find_one({"subscriptions": sub.id})
            if not user:
                print(f"  ❌ User not found for {sub.base_name}")
                failed_count += 1
                continue
            
            # Calculate remaining traffic if preserving
            old_config_count = len(sub.configs)
            remaining_traffic = sub.total_limit
            if preserve_traffic and sub.traffic_used > 0:
                remaining_traffic = max(0, sub.total_limit - sub.traffic_used)
                print(f"  💾 Preserving {sub.traffic_used / (1024**3):.2f}GB used, {remaining_traffic / (1024**3):.2f}GB remaining")
            
            sub.configs = []
            
            # Create new configs on all enabled panels
            new_configs = []
            
            for panel_key, panel_info in enabled_panels.items():
                try:
                    panel_service = XUIService(panel_key)
                    
                    # Get best inbounds for this panel
                    inbound_assignments = await inbound_balancer.get_balanced_inbounds(panel_key)
                    
                    # Create configs for each inbound type
                    for inbound_id in inbound_assignments:
                        client_uuid = str(uuid.uuid4())
                        client_email = f"{sub.base_name}_{panel_key}_inbound{inbound_id}"
                        
                        # Add client to panel
                        result = await panel_service.add_client(
                            inbound_id=inbound_id,
                            email=client_email,
                            uuid=client_uuid,
                            total_gb=remaining_traffic,
                            expire_time=int(sub.expires_at.timestamp() * 1000) if sub.expires_at else 0
                        )
                        
                        if result:
                            new_configs.append(ConfigItem(
                                panel_name=panel_info['name'],
                                inbound_id=inbound_id,
                                client_uuid=client_uuid,
                                client_email=client_email
                            ))
                            print(f"  ✅ Created on {panel_info['name']} inbound {inbound_id}")
                        else:
                            print(f"  ⚠️  Failed on {panel_info['name']} inbound {inbound_id}")
                    
                except Exception as e:
                    print(f"  ❌ Error on {panel_key}: {e}")
            
            if new_configs:
                sub.configs = new_configs
                if preserve_traffic:
                    # Keep current usage, update limit to remaining
                    sub.total_limit = remaining_traffic
                else:
                    # Reset traffic
                    sub.traffic_used = 0
                await sub.save()
                print(f"  ✅ Restored: {old_config_count} → {len(new_configs)} configs")
                success_count += 1
            else:
                print(f"  ❌ No configs created")
                failed_count += 1
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed_count += 1
    
    print("\n" + "=" * 50)
    print("📊 Restoration Complete!")
    print("=" * 50)
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"📦 Total: {len(subscriptions)}")
    print("\n💡 Users can now use their subscription links again!")

if __name__ == "__main__":
    asyncio.run(restore_all_users())
