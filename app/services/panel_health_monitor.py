"""
Panel Health Monitor & Automatic Disaster Recovery
Monitors panel health and automatically migrates users from failed panels
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from app.services.xui_service import XUIService
from app.core.panel_config import panel_config
from app.models.subscription import Subscription
from app.services.migration_service import migration_service
from app.core.config import settings
from telegram import Bot


class PanelHealthMonitor:
    def __init__(self):
        self.failed_panels = {}  # Track failed panels and failure count
        self.alert_sent = {}  # Track if alert was sent for a panel
        
    async def check_panel_health(self, panel_key: str) -> bool:
        """Check if a panel is healthy by attempting login"""
        try:
            panel_service = XUIService(panel_key)
            cookie = await panel_service.login()
            return cookie is not None
        except Exception as e:
            print(f"❌ Health check failed for {panel_key}: {e}")
            return False
    
    async def monitor_all_panels(self):
        """Monitor health of all enabled panels"""
        enabled_panels = panel_config.get_enabled_panels()
        health_status = {}
        
        for panel_key, panel_info in enabled_panels.items():
            is_healthy = await self.check_panel_health(panel_key)
            health_status[panel_key] = {
                "name": panel_info['name'],
                "healthy": is_healthy,
                "checked_at": datetime.utcnow()
            }
            
            if not is_healthy:
                # Track failures
                if panel_key not in self.failed_panels:
                    self.failed_panels[panel_key] = {"count": 1, "first_failed": datetime.utcnow()}
                else:
                    self.failed_panels[panel_key]["count"] += 1
                
                print(f"⚠️ Panel {panel_info['name']} is DOWN (failure #{self.failed_panels[panel_key]['count']})")
                
                # Auto-migrate after 3 consecutive failures
                if self.failed_panels[panel_key]["count"] >= 3:
                    await self.auto_migrate_from_failed_panel(panel_key, panel_info['name'])
            else:
                # Panel recovered
                if panel_key in self.failed_panels:
                    print(f"✅ Panel {panel_info['name']} RECOVERED")
                    del self.failed_panels[panel_key]
                    if panel_key in self.alert_sent:
                        del self.alert_sent[panel_key]
        
        return health_status
    
    async def auto_migrate_from_failed_panel(self, failed_panel_key: str, failed_panel_name: str):
        """Automatically migrate all users from failed panel to healthy panels"""
        try:
            # Check if auto-recovery is enabled
            if not panel_config.is_auto_recovery_enabled():
                print(f"ℹ️ Auto-recovery disabled, skipping migration for {failed_panel_name}")
                return
            
            # Prevent duplicate migrations
            if self.alert_sent.get(failed_panel_key):
                return
            
            print(f"🚨 AUTO-MIGRATION: Panel {failed_panel_name} is down, migrating users...")
            
            # Get all active subscriptions on failed panel
            subscriptions = await Subscription.find({
                "configs.panel_name": failed_panel_name,
                "is_active": True
            }).to_list()
            
            if not subscriptions:
                print(f"ℹ️ No active subscriptions found on {failed_panel_name}")
                return
            
            # Get healthy panels
            enabled_panels = panel_config.get_enabled_panels()
            healthy_panels = []
            for key, info in enabled_panels.items():
                if key != failed_panel_key:
                    is_healthy = await self.check_panel_health(key)
                    if is_healthy:
                        healthy_panels.append(key)
            
            if not healthy_panels:
                await self.send_critical_alert(failed_panel_name, len(subscriptions), "NO_HEALTHY_PANELS")
                return
            
            # Migrate users to healthy panels (round-robin)
            migrated = 0
            failed = 0
            
            for i, subscription in enumerate(subscriptions):
                target_panel = healthy_panels[i % len(healthy_panels)]
                
                try:
                    result = await migration_service.migrate_subscription(
                        subscription=subscription,
                        target_panel_key=target_panel,
                        reset_traffic=False  # Preserve traffic usage
                    )
                    
                    if result["success"]:
                        migrated += 1
                        print(f"✅ Migrated {subscription.base_name} to {target_panel}")
                    else:
                        failed += 1
                        print(f"❌ Failed to migrate {subscription.base_name}: {result.get('error')}")
                    
                    await asyncio.sleep(0.5)  # Avoid overwhelming panels
                    
                except Exception as e:
                    failed += 1
                    print(f"❌ Migration error for {subscription.base_name}: {e}")
            
            # Send alert
            await self.send_migration_alert(failed_panel_name, migrated, failed, healthy_panels)
            self.alert_sent[failed_panel_key] = datetime.utcnow()
            
        except Exception as e:
            print(f"❌ Auto-migration failed: {e}")
            await self.send_critical_alert(failed_panel_name, 0, str(e))
    
    async def send_migration_alert(self, failed_panel: str, migrated: int, failed: int, target_panels: List[str]):
        """Send alert about automatic migration"""
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            
            target_names = [panel_config.get_panel(p)['name'] for p in target_panels]
            
            text = f"🚨 **AUTOMATIC DISASTER RECOVERY**\n\n"
            text += f"❌ **Failed Panel:** {failed_panel}\n"
            text += f"✅ **Migrated Users:** {migrated}\n"
            text += f"❌ **Failed Migrations:** {failed}\n"
            text += f"🎯 **Target Panels:** {', '.join(target_names)}\n\n"
            text += f"⏰ **Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            text += f"ℹ️ All user traffic and expiry data preserved"
            
            admin_ids = settings.BOT_ADMIN_IDS.split(',')
            for admin_id in admin_ids:
                await bot.send_message(
                    chat_id=int(admin_id.strip()),
                    text=text,
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"❌ Failed to send migration alert: {e}")
    
    async def send_critical_alert(self, failed_panel: str, user_count: int, reason: str):
        """Send critical alert when migration cannot proceed"""
        try:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            
            text = f"🆘 **CRITICAL: MIGRATION FAILED**\n\n"
            text += f"❌ **Failed Panel:** {failed_panel}\n"
            text += f"👥 **Affected Users:** {user_count}\n"
            text += f"⚠️ **Reason:** {reason}\n\n"
            text += f"🔧 **ACTION REQUIRED:** Manual intervention needed!"
            
            admin_ids = settings.BOT_ADMIN_IDS.split(',')
            for admin_id in admin_ids:
                await bot.send_message(
                    chat_id=int(admin_id.strip()),
                    text=text,
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"❌ Failed to send critical alert: {e}")
    
    async def get_health_report(self) -> Dict:
        """Get current health status of all panels"""
        health_status = await self.monitor_all_panels()
        
        return {
            "timestamp": datetime.utcnow(),
            "panels": health_status,
            "failed_panels": self.failed_panels,
            "total_panels": len(health_status),
            "healthy_panels": sum(1 for p in health_status.values() if p["healthy"])
        }


panel_health_monitor = PanelHealthMonitor()


async def start_panel_health_monitor():
    """Start background panel health monitoring"""
    async def monitor_loop():
        while True:
            try:
                print(f"🏥 [{datetime.utcnow()}] Checking panel health...")
                report = await panel_health_monitor.get_health_report()
                print(f"✅ Health check complete: {report['healthy_panels']}/{report['total_panels']} panels healthy")
            except Exception as e:
                print(f"❌ Health monitor error: {e}")
            
            # Check interval from config
            interval = panel_config.get_health_check_interval()
            await asyncio.sleep(interval)
    
    asyncio.create_task(monitor_loop())
    print("✅ Panel health monitor started")
