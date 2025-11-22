#!/usr/bin/env python3
"""
Clean up server load data for disabled/removed servers
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import connect_to_mongo, init_db
from app.models.server_load import ServerLoad
from app.core.panel_config import panel_config

async def cleanup_servers():
    """Remove server load data for disabled/removed servers"""
    await connect_to_mongo()
    await init_db()
    
    # Get enabled panels
    enabled_panels = panel_config.get_enabled_panels()
    enabled_names = [info['name'] for info in enabled_panels.values()]
    
    print(f"✅ Enabled panels: {enabled_names}")
    
    # Get all server loads
    all_servers = await ServerLoad.find().to_list()
    
    for server in all_servers:
        if server.panel_name not in enabled_names:
            print(f"🗑️ Removing disabled server: {server.panel_name}")
            await server.delete()
        else:
            print(f"✅ Keeping enabled server: {server.panel_name}")
    
    print("\n🎉 Server cleanup completed!")

if __name__ == "__main__":
    asyncio.run(cleanup_servers())