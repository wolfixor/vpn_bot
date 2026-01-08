"""
Subscription Migration Service
Handles transferring subscriptions between different VPN panels
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.models.subscription import Subscription, ConfigItem
from app.services.xui_service import XUIService
from app.core.panel_config import panel_config
from app.core.logger import logger


class MigrationService:
    def __init__(self):
        pass

    async def migrate_subscription(self, subscription: Subscription, target_panel_key: str, reset_traffic: bool = True) -> Dict[str, Any]:
        """Migrate a subscription from current panel(s) to target panel"""
        try:
            if not subscription.configs:
                return {"success": False, "error": "No configs found in subscription"}

            # Get target panel info
            target_panels = panel_config.get_enabled_panels()
            if target_panel_key not in target_panels:
                return {"success": False, "error": f"Target panel {target_panel_key} not found or disabled"}
            
            target_panel_info = target_panels[target_panel_key]
            target_service = XUIService(target_panel_key)

            # Get unique source panels from all configs
            source_panels = {}
            for config in subscription.configs:
                panel_key, panel_info = panel_config.get_panel_by_name(config.panel_name)
                if panel_key and panel_key not in source_panels:
                    source_panels[panel_key] = {
                        "info": panel_info,
                        "service": XUIService(panel_key),
                        "configs": []
                    }
                if panel_key:
                    source_panels[panel_key]["configs"].append(config)

            # Get current traffic usage before migration
            current_usage = 0
            if not reset_traffic:
                try:
                    for panel_key, panel_data in source_panels.items():
                        for config in panel_data["configs"]:
                            client_stats = await panel_data["service"].get_client_stats(config.inbound_id, config.client_uuid)
                            if client_stats:
                                current_usage += client_stats.get('down', 0) + client_stats.get('up', 0)
                except Exception as e:
                    logger.warning(f"Could not get traffic stats: {e}")

            # Create new configs on target panel
            new_configs = []
            expiry_timestamp = int(subscription.expires_at.timestamp() * 1000) if subscription.expires_at else None
            remaining_traffic = max(0, subscription.total_limit - current_usage) if not reset_traffic else subscription.total_limit

            # Get target panel inbounds
            from app.services.inbound_balancer import inbound_balancer
            target_inbounds = await inbound_balancer.get_balanced_inbounds(target_panel_key)

            for inbound_info in target_inbounds:
                inbound_data = inbound_info["data"]
                inbound_id = inbound_data["id"]
                client_id = str(uuid.uuid4())
                client_email = f"{subscription.base_name}_{target_panel_key}_inbound{inbound_id}"

                result = await target_service.add_client(
                    inbound_id=inbound_id,
                    client_email=client_email,
                    client_id=client_id,
                    total_gb=remaining_traffic,
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

            if not new_configs:
                return {"success": False, "error": "Failed to create configs on target panel"}

            # Delete old configs from ALL source panels
            deleted_count = 0
            for panel_key, panel_data in source_panels.items():
                for config in panel_data["configs"]:
                    try:
                        success = await panel_data["service"].delete_client(config.inbound_id, config.client_uuid)
                        if success:
                            deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete config from {panel_key}: {e}")

            # Update subscription with new configs and migration history
            source_panel_names = [p["info"]["name"] for p in source_panels.values()]
            subscription.configs = new_configs
            if not reset_traffic:
                subscription.traffic_used = current_usage
            else:
                subscription.traffic_used = 0
            
            # Track migration history for sync optimization
            subscription.migration_history = {
                "from": source_panel_names,
                "to": target_panel_info['name'],
                "migrated_at": datetime.utcnow(),
                "reason": "manual_migration"
            }
            
            await subscription.save()

            # Update load balancer - deallocate from ALL source panels
            from app.services.load_balancer import load_balancer
            for panel_key in source_panels.keys():
                await load_balancer.deallocate_subscription_from_server(panel_key)
            await load_balancer.allocate_subscription_to_server(target_panel_key)

            logger.info(f"Subscription {subscription.subscription_token} migrated from {source_panel_names} to {target_panel_key}")
            
            return {
                "success": True,
                "message": f"Subscription migrated from {', '.join(source_panel_names)} to {target_panel_info['name']}",
                "new_configs_count": len(new_configs),
                "deleted_configs_count": deleted_count,
                "traffic_preserved": not reset_traffic
            }

        except Exception as e:
            logger.error(f"Migration failed for subscription {subscription.subscription_token}: {str(e)}")
            return {"success": False, "error": str(e)}

    async def bulk_migrate_subscriptions(self, subscription_tokens: List[str], target_panel_key: str, reset_traffic: bool = True) -> Dict:
        """Migrate multiple subscriptions in batch"""
        results = {"successful": [], "failed": []}
        
        for token in subscription_tokens:
            try:
                subscription = await Subscription.find_one(Subscription.subscription_token == token)
                if not subscription:
                    results["failed"].append({"token": token, "error": "Subscription not found"})
                    continue

                result = await self.migrate_subscription(subscription, target_panel_key, reset_traffic)
                if result["success"]:
                    results["successful"].append(token)
                else:
                    results["failed"].append({"token": token, "error": result["error"]})
                
                # Small delay to avoid overwhelming panels
                await asyncio.sleep(0.5)
            except Exception as e:
                results["failed"].append({"token": token, "error": str(e)})
        
        return {
            "success": True,
            "migrated": len(results["successful"]),
            "failed": len(results["failed"]),
            "details": results
        }

    async def auto_balance_panels(self) -> Dict:
        """Automatically balance subscriptions across available panels"""
        try:
            # Get all active panels
            enabled_panels = panel_config.get_enabled_panels()
            if len(enabled_panels) < 2:
                return {"success": False, "error": "Need at least 2 panels for balancing"}

            # Get subscription distribution by panel
            distribution = {}
            for panel_key in enabled_panels.keys():
                panel_name = enabled_panels[panel_key]['name']
                count = await Subscription.find({"configs.panel_name": panel_name, "is_active": True}).count()
                distribution[panel_key] = count

            # Find overloaded and underloaded panels
            avg_subs = sum(distribution.values()) / len(distribution)
            overloaded = {k: v for k, v in distribution.items() if v > avg_subs * 1.2}
            underloaded = {k: v for k, v in distribution.items() if v < avg_subs * 0.8}

            if not overloaded or not underloaded:
                return {"success": True, "message": "Panels are already balanced"}

            # Migrate subscriptions from overloaded to underloaded panels
            migrations = []
            for source_panel_key, source_count in overloaded.items():
                source_panel_name = enabled_panels[source_panel_key]['name']
                excess = int(source_count - avg_subs)
                
                # Get subscriptions to migrate
                subs_to_migrate = await Subscription.find(
                    {"configs.panel_name": source_panel_name, "is_active": True}
                ).limit(excess).to_list(excess)

                for target_key in underloaded:
                    if not subs_to_migrate:
                        break
                    
                    subscription = subs_to_migrate.pop()
                    result = await self.migrate_subscription(subscription, target_key, reset_traffic=False)
                    migrations.append(result)
                    
                    # Update distribution
                    distribution[source_panel_key] -= 1
                    distribution[target_key] += 1

            return {
                "success": True,
                "message": "Auto-balancing completed",
                "migrations": len([m for m in migrations if m.get('success')])
            }

        except Exception as e:
            logger.error(f"Auto-balance failed: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_migration_stats(self) -> Dict:
        """Get migration statistics"""
        try:
            # Panel distribution
            enabled_panels = panel_config.get_enabled_panels()
            distribution = []
            
            for panel_key, panel_info in enabled_panels.items():
                count = await Subscription.find({"configs.panel_name": panel_info['name'], "is_active": True}).count()
                distribution.append({
                    "panel_key": panel_key,
                    "panel_name": panel_info['name'],
                    "count": count,
                    "flag": panel_info.get('flag', '🌐')
                })
            
            distribution.sort(key=lambda x: x['count'], reverse=True)

            # Total active subscriptions
            total_subscriptions = await Subscription.find({"is_active": True}).count()

            return {
                "success": True,
                "panel_distribution": distribution,
                "total_subscriptions": total_subscriptions,
                "enabled_panels": len(enabled_panels)
            }

        except Exception as e:
            logger.error(f"Failed to get migration stats: {str(e)}")
            return {"success": False, "error": str(e)}


migration_service = MigrationService()