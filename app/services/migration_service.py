from typing import List, Dict, Any
from app.models.subscription import Subscription, ConfigItem
from app.services.xui_service import XUIService
from app.services.load_balancer import load_balancer
from app.core.panel_config import panel_config
import uuid

class MigrationService:
    """Handle migration of subscriptions between panels"""
    
    async def migrate_subscription(self, subscription: Subscription, target_panel_key: str, reset_traffic: bool = True) -> Dict[str, Any]:
        """Migrate a subscription from current panel to target panel
        
        Args:
            subscription: Subscription to migrate
            target_panel_key: Target panel key
            reset_traffic: True = reset used traffic, False = preserve used traffic
        """
        
        # Get target panel info
        target_panel_info = panel_config.get_panel(target_panel_key)
        if not target_panel_info:
            return {"success": False, "error": f"Target panel {target_panel_key} not found"}
        
        # Get current panel info
        current_configs = subscription.configs
        if not current_configs:
            return {"success": False, "error": "No configs to migrate"}
        
        current_panel_name = current_configs[0].panel_name
        
        # Don't migrate if already on target panel
        if current_panel_name.lower() == target_panel_info['name'].lower():
            return {"success": False, "error": "Already on target panel"}
        
        print(f"🔄 Migrating subscription {subscription.base_name} from {current_panel_name} to {target_panel_info['name']}")
        
        # Calculate traffic limit based on reset_traffic flag
        if reset_traffic:
            # Reset: Give full traffic back
            traffic_limit = subscription.total_limit or 0
            print(f"  💾 Reset traffic: {traffic_limit / (1024**3):.2f}GB (full)")
        else:
            # Preserve: Subtract used traffic from total
            used_traffic = subscription.traffic_used or 0
            remaining_traffic = max(0, (subscription.total_limit or 0) - used_traffic)
            traffic_limit = remaining_traffic
            print(f"  💾 Preserve traffic: {remaining_traffic / (1024**3):.2f}GB (used: {used_traffic / (1024**3):.2f}GB)")
        
        # Create new configs on target panel
        new_configs = []
        target_service = XUIService(target_panel_key)
        
        # Get target panel inbounds
        inbounds_response = await target_service.get_inbounds()
        if not inbounds_response or not inbounds_response.get("success"):
            return {"success": False, "error": "Failed to get target panel inbounds"}
        
        # Create configs on target panel
        expiry_timestamp = int(subscription.expires_at.timestamp() * 1000) if subscription.expires_at else 0
        
        for inbound_data in inbounds_response.get("obj", []):
            if not inbound_data.get("enable", True):
                continue
            
            inbound_id = inbound_data["id"]
            client_id = str(uuid.uuid4())
            client_email = f"{subscription.base_name}_{target_panel_key}_inbound{inbound_id}"
            
            result = await target_service.add_client(
                inbound_id=inbound_id,
                client_email=client_email,
                client_id=client_id,
                total_gb=traffic_limit,
                expire_time=expiry_timestamp
            )
            
            if result and result.get("success"):
                protocol = inbound_data.get("protocol", "vless")
                stored_id = client_id[:10] if protocol == "trojan" else client_id
                
                config_item = ConfigItem(
                    panel_name=target_panel_info['name'],
                    inbound_id=inbound_id,
                    client_uuid=stored_id,
                    client_email=client_email,
                    client_password=client_id[:10] if protocol == "trojan" else None
                )
                new_configs.append(config_item)
                print(f"  ✅ Created config on {target_panel_info['name']} inbound {inbound_id}")
        
        if not new_configs:
            return {"success": False, "error": "Failed to create configs on target panel"}
        
        # Delete old configs
        deleted_count = 0
        old_panel_key = None
        
        for config in current_configs:
            try:
                # Find panel key for old config
                panel_key, panel_info = panel_config.get_panel_by_name(config.panel_name)
                if panel_key:
                    old_panel_key = panel_key
                    old_service = XUIService(panel_key)
                    success = await old_service.delete_client(config.inbound_id, config.client_uuid)
                    if success:
                        deleted_count += 1
                        print(f"  ✅ Deleted from {config.panel_name} inbound {config.inbound_id}")
            except Exception as e:
                print(f"  ❌ Error deleting from {config.panel_name}: {e}")
        
        # Update subscription with new configs
        subscription.configs = new_configs
        
        # Update total_limit if traffic was preserved
        if not reset_traffic:
            subscription.total_limit = traffic_limit
            subscription.traffic_used = 0  # Reset counter on new panel
            print(f"  📊 Updated subscription total_limit to {traffic_limit / (1024**3):.2f}GB")
        
        await subscription.save()
        
        # Update load balancer
        if old_panel_key:
            await load_balancer.deallocate_subscription_from_server(current_panel_name)
        await load_balancer.allocate_subscription_to_server(target_panel_key)
        
        return {
            "success": True,
            "migrated_from": current_panel_name,
            "migrated_to": target_panel_info['name'],
            "new_configs": len(new_configs),
            "deleted_configs": deleted_count
        }
    
    async def migrate_users_from_panel(self, source_panel_name: str, target_panel_key: str, max_users: int = 10, reset_traffic: bool = True) -> Dict[str, Any]:
        """Migrate multiple users from source panel to target panel
        
        Args:
            source_panel_name: Source panel name
            target_panel_key: Target panel key
            max_users: Maximum users to migrate
            reset_traffic: True = reset used traffic, False = preserve used traffic
        """
        
        # Get subscriptions on source panel
        subscriptions = await Subscription.find(Subscription.is_active == True).to_list()
        
        source_subscriptions = []
        for sub in subscriptions:
            if any(config.panel_name.lower() == source_panel_name.lower() for config in sub.configs):
                source_subscriptions.append(sub)
        
        if not source_subscriptions:
            return {"success": False, "error": f"No subscriptions found on {source_panel_name}"}
        
        # Limit migration count
        to_migrate = source_subscriptions[:max_users]
        
        results = []
        success_count = 0
        
        for sub in to_migrate:
            try:
                result = await self.migrate_subscription(sub, target_panel_key, reset_traffic)
                results.append({
                    "subscription": sub.base_name,
                    "result": result
                })
                if result.get("success"):
                    success_count += 1
            except Exception as e:
                results.append({
                    "subscription": sub.base_name,
                    "result": {"success": False, "error": str(e)}
                })
        
        return {
            "success": True,
            "total_attempted": len(to_migrate),
            "successful_migrations": success_count,
            "failed_migrations": len(to_migrate) - success_count,
            "results": results
        }
    
    async def balance_servers(self) -> Dict[str, Any]:
        """Auto-balance users across servers based on capacity"""
        
        # Get server loads
        await load_balancer.sync_server_loads()
        
        from app.models.server_load import ServerLoad
        servers = await ServerLoad.find(ServerLoad.is_active == True).sort(+ServerLoad.current_subscriptions).to_list()
        
        if len(servers) < 2:
            return {"success": False, "error": "Need at least 2 servers for balancing"}
        
        # Find overloaded and underloaded servers
        total_subscriptions = sum(s.current_subscriptions for s in servers)
        total_capacity = sum(s.max_subscriptions for s in servers)
        average_load = total_subscriptions / len(servers)
        
        # Get balance threshold from YAML settings
        yaml_settings = panel_config.load().get('settings', {})
        balance_threshold = yaml_settings.get('balance_threshold', 3)
        
        overloaded = [s for s in servers if s.current_subscriptions > average_load + balance_threshold]
        underloaded = [s for s in servers if s.current_subscriptions < average_load - balance_threshold]
        
        if not overloaded or not underloaded:
            return {"success": False, "error": "Servers already balanced"}
        
        migrations = []
        
        for overloaded_server in overloaded:
            for underloaded_server in underloaded:
                if overloaded_server.current_subscriptions <= average_load:
                    break
                
                # Calculate how many to migrate
                excess = overloaded_server.current_subscriptions - int(average_load)
                capacity = underloaded_server.max_subscriptions - underloaded_server.current_subscriptions
                to_migrate = min(excess, capacity, 5)  # Max 5 at a time
                
                if to_migrate > 0:
                    # Find target panel key
                    target_panel_key = None
                    enabled_panels = panel_config.get_enabled_panels()
                    for key, info in enabled_panels.items():
                        if info['name'] == underloaded_server.panel_name:
                            target_panel_key = key
                            break
                    
                    if target_panel_key:
                        result = await self.migrate_users_from_panel(
                            overloaded_server.panel_name,
                            target_panel_key,
                            to_migrate,
                            reset_traffic=False  # Always preserve traffic in auto-balance
                        )
                        migrations.append({
                            "from": overloaded_server.panel_name,
                            "to": underloaded_server.panel_name,
                            "attempted": to_migrate,
                            "result": result
                        })
                        
                        # Update counts for next iteration
                        if result.get("success"):
                            successful = result.get("successful_migrations", 0)
                            overloaded_server.current_subscriptions -= successful
                            underloaded_server.current_subscriptions += successful
        
        return {
            "success": True,
            "migrations": migrations,
            "total_migrations": len(migrations)
        }

migration_service = MigrationService()