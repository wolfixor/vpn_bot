"""Setup load balancing system"""
import asyncio
from app.database.database import init_db
from app.models.server_load import ServerLoad
from app.services.load_balancer import load_balancer

async def setup():
    """Initialize load balancing system"""
    await init_db()
    
    print("🔄 Setting up load balancing system...\n")
    
    # Sync current server loads from panels
    print("📊 Syncing server loads from panels...")
    await load_balancer.sync_server_loads()
    
    # Display current status
    servers = await ServerLoad.find().to_list()
    
    if not servers:
        print("⚠️ No servers found. Make sure panels are configured and have inbounds.")
        return
    
    print(f"\n✅ Found {len(servers)} servers:\n")
    print("┌─────────────────────────────────────────────────────────┐")
    print("│ Panel          │ Inbound │ Type    │ Users │ Max │ %   │")
    print("├─────────────────────────────────────────────────────────┤")
    
    for server in servers:
        usage_pct = (server.current_users / server.max_users * 100) if server.max_users > 0 else 0
        status = "🟢" if usage_pct < 70 else "🟡" if usage_pct < 90 else "🔴"
        
        print(f"│ {status} {server.panel_name:12} │ {server.inbound_id:7} │ {server.server_type:7} │ {server.current_users:5} │ {server.max_users:3} │ {usage_pct:3.0f}% │")
    
    print("└─────────────────────────────────────────────────────────┘\n")
    
    # Update server limits if needed
    print("💡 To update server limits:")
    print("   - Auto by CPU: server.cpu_cores = 2; server.update_max_users_by_cpu()")
    print("   - Manual: server.max_users = 60")
    print("\n✅ Load balancing system ready!")

if __name__ == "__main__":
    asyncio.run(setup())
