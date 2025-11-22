#!/usr/bin/env python3
"""
Manual migration script for moving users between panels
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import connect_to_mongo, init_db
from app.services.migration_service import migration_service
from app.core.panel_config import panel_config

async def main():
    await connect_to_mongo()
    await init_db()
    
    print("🔄 VPN User Migration Tool")
    print("=" * 40)
    
    # Show available panels
    enabled_panels = panel_config.get_enabled_panels()
    print("\n📋 Available Panels:")
    for key, info in enabled_panels.items():
        print(f"  {key}: {info['name']} ({info['flag']})")
    
    print("\n🎯 Migration Options:")
    print("1. Migrate specific users from panel A to panel B")
    print("2. Auto-balance all servers")
    print("3. Show server status")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        # Manual migration
        source = input("Source panel name (e.g., Germany): ").strip()
        target_key = input("Target panel key (e.g., server2): ").strip()
        max_users = int(input("Max users to migrate (default 10): ").strip() or "10")
        
        print(f"\n🔄 Migrating up to {max_users} users from {source} to {target_key}...")
        result = await migration_service.migrate_users_from_panel(source, target_key, max_users)
        
        if result.get("success"):
            print(f"✅ Migration completed!")
            print(f"   Attempted: {result['total_attempted']}")
            print(f"   Successful: {result['successful_migrations']}")
            print(f"   Failed: {result['failed_migrations']}")
        else:
            print(f"❌ Migration failed: {result.get('error')}")
    
    elif choice == "2":
        # Auto-balance
        print("\n⚖️ Auto-balancing servers...")
        result = await migration_service.balance_servers()
        
        if result.get("success"):
            print(f"✅ Balancing completed!")
            print(f"   Total migrations: {result['total_migrations']}")
            for migration in result['migrations']:
                print(f"   {migration['from']} → {migration['to']}: {migration['attempted']} users")
        else:
            print(f"❌ Balancing failed: {result.get('error')}")
    
    elif choice == "3":
        # Show status
        from app.models.server_load import ServerLoad
        from app.services.load_balancer import load_balancer
        
        await load_balancer.sync_server_loads()
        servers = await ServerLoad.find().to_list()
        
        print("\n📊 Server Status:")
        for server in servers:
            usage = (server.current_subscriptions / server.max_subscriptions) * 100
            status = "🟢" if usage < 70 else "🟡" if usage < 90 else "🔴"
            print(f"  {status} {server.panel_name}: {server.current_subscriptions}/{server.max_subscriptions} ({usage:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())