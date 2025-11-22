from typing import Optional
from app.models.server_load import ServerLoad
from app.core.config import settings
from app.core.panel_config import panel_config
from telegram import Bot
import asyncio
from datetime import datetime

class LoadBalancerService:
    """Manage server load balancing and capacity alerts"""
    
    ALERT_CHANNEL_ID = settings.PAYMENT_CHANNEL_ID
    
    async def get_available_server(self) -> Optional[str]:
        """Get available server with capacity - NEVER stop creating users, just alert"""
        # Always sync first to get accurate counts
        await self.sync_server_loads()
        
        # Get only enabled servers
        enabled_names = [info['name'] for info in panel_config.get_enabled_panels().values()]
        servers = await ServerLoad.find(
            {"is_active": True, "panel_name": {"$in": enabled_names}}
        ).sort(+ServerLoad.current_subscriptions).to_list()
        
        if not servers:
            # No servers configured, use first enabled panel
            enabled_panels = panel_config.get_enabled_panels()
            return list(enabled_panels.keys())[0] if enabled_panels else list(panel_config.load()['panels'].keys())[0]
        
        # Find server with capacity - prefer servers under 80% load
        for server in servers:
            if server.can_accept_subscription():
                usage_percent = (server.current_subscriptions / server.max_subscriptions) * 100
                print(f"🟢 Selected {server.panel_name}: {server.current_subscriptions}/{server.max_subscriptions} ({usage_percent:.1f}%)")
                # Get panel key from panel name
                enabled_panels = panel_config.get_enabled_panels()
                for key, info in enabled_panels.items():
                    if info['name'] == server.panel_name:
                        return key
                return server.panel_name
        
        # All servers full - send alert but use lowest load anyway
        await self.send_capacity_alert()
        lowest_load_server = servers[0]  # Already sorted by current_subscriptions
        usage_percent = (lowest_load_server.current_subscriptions / lowest_load_server.max_subscriptions) * 100
        print(f"🟡 All servers full - using {lowest_load_server.panel_name} anyway ({usage_percent:.1f}%)")
        # Get panel key from panel name
        enabled_panels = panel_config.get_enabled_panels()
        for key, info in enabled_panels.items():
            if info['name'] == lowest_load_server.panel_name:
                return key
        return lowest_load_server.panel_name
    
    async def allocate_subscription_to_server(self, panel_name: str) -> bool:
        """Allocate a subscription to server - track subscription count not inbound count"""
        # Find panel dynamically
        panel_key, panel_info = panel_config.get_panel_by_name(panel_name)
        if not panel_key:
            panel_info = panel_config.get_panel(panel_name)
            panel_key = panel_name
        
        if not panel_info:
            print(f"⚠️ Panel {panel_name} not found")
            return False
        
        server = await ServerLoad.find_one(ServerLoad.panel_name == panel_info['name'])
        
        if not server:
            server = ServerLoad(
                panel_name=panel_info['name'],
                current_subscriptions=1,  # Start with 1
                max_subscriptions=panel_info.get('max_users', 50),
                is_active=panel_info.get('enabled', True)
            )
        else:
            server.increment_subscriptions()
        
        await server.save()
        
        print(f"📈 Allocated subscription to {server.panel_name}: {server.current_subscriptions}/{server.max_subscriptions}")
        
        # Check if approaching capacity (90%)
        capacity_ratio = server.current_subscriptions / server.max_subscriptions
        if capacity_ratio >= 0.9 and not server.alert_sent:
            await self.send_approaching_capacity_alert(server)
            server.alert_sent = True
            await server.save()
        elif capacity_ratio >= 1.0:
            await self.send_capacity_alert()
        
        return True
    
    async def deallocate_subscription_from_server(self, panel_name: str):
        """Remove subscription from server - handle name variations"""
        # Find server dynamically
        server = await ServerLoad.find_one(ServerLoad.panel_name == panel_name)
        
        if not server:
            panel_key, panel_info = panel_config.get_panel_by_name(panel_name)
            if panel_info:
                server = await ServerLoad.find_one(ServerLoad.panel_name == panel_info['name'])
        
        if server and server.current_subscriptions > 0:
            server.decrement_subscriptions()
            await server.save()
            print(f"📉 Deallocated subscription from {server.panel_name}: {server.current_subscriptions}/{server.max_subscriptions}")
            
            # Reset alert flag if capacity drops below 90%
            if server.current_subscriptions < server.max_subscriptions * 0.9:
                server.alert_sent = False
                await server.save()
        else:
            print(f"⚠️ Could not deallocate from {panel_name} - server not found or already at 0")
    
    async def send_capacity_alert(self):
        """Send alert when all servers at capacity - but still creating users"""
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            
            # Get current server status
            servers = await ServerLoad.find().to_list()
            server_status = "\n".join([
                f"🟡 {s.panel_name}: {s.current_subscriptions}/{s.max_subscriptions} ({(s.current_subscriptions/s.max_subscriptions)*100:.1f}%)"
                for s in servers
            ])
            
            text = f"🚨 **هشدار ظرفیت سرور**\n\n"
            text += f"⚠️ **وضعیت:** تمام سرورها پر هستند\n\n"
            text += f"📊 **وضعیت فعلی:**\n{server_status}\n\n"
            text += f"🔄 **توجه:** کاربران جدید همچنان ایجاد می‌شوند\n"
            text += f"**اقدام لازم:** افزودن سرور جدید یا افزایش ظرفیت"
            
            await bot.send_message(
                chat_id=self.ALERT_CHANNEL_ID,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Error sending capacity alert: {e}")
    
    async def send_approaching_capacity_alert(self, server: ServerLoad):
        """Send alert when server approaching 90% capacity"""
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            usage_percent = (server.current_subscriptions / server.max_subscriptions) * 100
            
            text = f"⚠️ **هشدار ظرفیت**\n\n"
            text += f"📍 **سرور:** {server.panel_name.upper()}\n"
            text += f"👥 **اشتراک‌ها:** {server.current_subscriptions}/{server.max_subscriptions}\n"
            text += f"📊 **استفاده:** {usage_percent:.1f}%\n\n"
            text += f"🔄 **وضعیت:** نزدیک به پر شدن\n"
            text += f"**توصیه:** آماده سازی سرور جدید یا افزایش ظرفیت"
            
            await bot.send_message(
                chat_id=self.ALERT_CHANNEL_ID,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"❌ Error sending approaching capacity alert: {e}")
    
    async def sync_server_loads(self):
        """Sync server loads from active subscriptions - only enabled servers"""
        from app.models.subscription import Subscription
        
        # Remove disabled servers first
        enabled_panels = panel_config.get_enabled_panels()
        enabled_names = [info['name'] for info in enabled_panels.values()]
        
        # Delete servers not in enabled list
        all_servers = await ServerLoad.find().to_list()
        for server in all_servers:
            if server.panel_name not in enabled_names:
                print(f"🗑️ Removing disabled server: {server.panel_name}")
                await server.delete()
        
        # Sync enabled servers
        for panel_name, panel_info in enabled_panels.items():
            try:
                # Count active subscriptions that have configs on this panel
                subscriptions = await Subscription.find(Subscription.is_active == True).to_list()
                
                # Count unique subscriptions (not inbounds) that use this panel
                subscription_count = 0
                for sub in subscriptions:
                    # Check if this subscription has any config on this panel
                    has_config_on_panel = any(
                        config.panel_name.lower().replace(' ', '') == panel_info['name'].lower().replace(' ', '')
                        for config in sub.configs
                    )
                    if has_config_on_panel:
                        subscription_count += 1
                
                server = await ServerLoad.find_one(ServerLoad.panel_name == panel_info['name'])
                
                if not server:
                    server = ServerLoad(
                        panel_name=panel_info['name'],
                        current_subscriptions=subscription_count,
                        max_subscriptions=panel_info.get('max_users', 50),
                        is_active=True
                    )
                else:
                    server.current_subscriptions = subscription_count
                    server.max_subscriptions = panel_info.get('max_users', 50)
                    server.is_active = True
                    server.is_full = subscription_count >= server.max_subscriptions
                
                await server.save()
                print(f"✅ Synced {panel_info['name']}: {subscription_count} subscriptions (max: {server.max_subscriptions})")
                    
            except Exception as e:
                print(f"❌ Error syncing {panel_name}: {e}")

async def start_load_balancer_sync():
    """Start background task to sync server loads every 10 minutes"""
    async def sync_loop():
        while True:
            try:
                print(f"🔄 [{datetime.now()}] Syncing server loads...")
                await load_balancer.sync_server_loads()
                
                # Check if auto-balance is needed
                from app.models.server_load import ServerLoad
                servers = await ServerLoad.find(ServerLoad.is_active == True).to_list()
                
                if len(servers) >= 2:
                    total_subs = sum(s.current_subscriptions for s in servers)
                    avg_load = total_subs / len(servers)
                    
                    # Get balance threshold from YAML settings
                    yaml_settings = panel_config.load().get('settings', {})
                    balance_threshold = yaml_settings.get('balance_threshold', 3)
                    
                    # Check if any server is significantly imbalanced
                    needs_balance = any(
                        abs(s.current_subscriptions - avg_load) > balance_threshold for s in servers
                    )
                    
                    if needs_balance:
                        print(f"⚠️ Imbalance detected - triggering auto-balance...")
                        from app.services.migration_service import migration_service
                        result = await migration_service.balance_servers()
                        if result.get("success"):
                            print(f"✅ Auto-balance completed: {result.get('total_migrations', 0)} migrations")
                        else:
                            print(f"ℹ️ {result.get('error', 'No balance needed')}")
                    else:
                        print(f"✅ Servers balanced - no migration needed")
                        
            except Exception as e:
                print(f"❌ Error in load balancer sync: {e}")
            
            # Sync every 10 minutes (600 seconds)
            await asyncio.sleep(600)
    
    asyncio.create_task(sync_loop())
    print("✅ Load balancer sync started")

load_balancer = LoadBalancerService()
