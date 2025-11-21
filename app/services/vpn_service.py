import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from app.services.xui_service import XUIService
from app.models.order import Order
from app.models.user import User

from app.services.auto_config_generator import AutoConfigGenerator
from app.models.subscription import Subscription
from app.core.config import settings

class VPNService:
    
    # Simple panel configuration
    ENABLED_PANELS = {
        "germany": {
            "name": "Germany",
            "ip": "185.110.188.73",
            "flag": "🇩🇪"
        },
        # "turkey": {
        #     "name": "Turkey",
        #     "ip": "91.216.104.8",
        #     "flag": "🇹🇷"
        # }
    }
    
    async def create_multi_panel_config(self, order: Order, config_name: str = None) -> Dict[str, Any]:
        """Create VPN configs in all enabled panels"""
        from app.models.subscription import ConfigItem
        
        # Get user and plan
        user = await order.user.fetch() if hasattr(order.user, 'fetch') else order.user
        vpn_plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
        
        # Generate unique subscription token for this order
        subscription_token = str(uuid.uuid4())
        
        # Calculate expiry
        expiry_date = datetime.utcnow() + timedelta(days=vpn_plan.duration_days)
        expiry_timestamp = int(expiry_date.timestamp() * 1000)
        total_gb = vpn_plan.traffic_limit_gb * 1024 * 1024 * 1024 if vpn_plan.traffic_limit_gb else 0
        
        # Generate base name for this purchase
        base_uuid = str(uuid.uuid4())
        if config_name:
            base_name = f"{config_name}_{base_uuid[:8]}"
        else:
            base_name = f"user_{user.telegram_id}_{base_uuid[:8]}"
        
        config_items = []
        all_config_urls = []
        
        # Add clients to existing inbounds in all enabled panels
        for panel_name, panel_info in self.ENABLED_PANELS.items():
            panel_service = XUIService(panel_name)
            
            # Get existing inbounds from the panel
            inbounds_response = await panel_service.get_inbounds()
            if not inbounds_response or not inbounds_response.get("success"):
                continue
                
            existing_inbounds = inbounds_response.get("obj", [])
            print(f"📊 Total inbounds from {panel_name}: {len(existing_inbounds)}")
            
            # Add clients to existing inbounds
            for inbound_data in existing_inbounds:
                print(f"🔍 Inbound {inbound_data['id']}: enabled={inbound_data.get('enable', True)}, protocol={inbound_data.get('protocol')}")
                if not inbound_data.get("enable", True):
                    continue
                    
                inbound_id = inbound_data["id"]
                client_id = str(uuid.uuid4())  # Unique UUID for each inbound
                
                # Make email unique per inbound to avoid duplicate errors
                client_email = f"{base_name}_inbound{inbound_id}"
                
                # Add client to existing inbound
                print(f"➕ Adding client to inbound {inbound_id} on {panel_name}...")
                result = await panel_service.add_client(
                    inbound_id=inbound_id,
                    client_email=client_email,
                    client_id=client_id,
                    total_gb=total_gb,
                    expire_time=expiry_timestamp
                )
                
                print(f"📝 Result for inbound {inbound_id}: {result}")
                
                if result and result.get("success"):
                    print(f"✅ Successfully added client to inbound {inbound_id}")
                    try:
                        # For Trojan, store password instead of UUID
                        protocol = inbound_data.get("protocol", "vless")
                        stored_id = client_id[:10] if protocol == "trojan" else client_id
                        
                        # Create ConfigItem
                        config_item = ConfigItem(
                            panel_name=panel_info['name'],
                            inbound_id=inbound_id,
                            client_uuid=stored_id,
                            client_email=client_email,
                            client_password=client_id[:10] if protocol == "trojan" else None
                        )
                        config_items.append(config_item)
                        
                        # Generate config URL using raw inbound data
                        config_url = self.generate_config_url_from_item(config_item, inbound_data, panel_info['ip'])
                        if config_url:
                            all_config_urls.append({
                                "config": config_url,
                                "panel_flag": panel_info['flag']
                            })
                    except Exception as e:
                        print(f"❌ Error processing inbound {inbound_id}: {str(e)}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"❌ Failed to add client to inbound {inbound_id}: {result}")
        
        # Create ONE Subscription record for this purchase with unique token
        subscription = Subscription(
            subscription_token=subscription_token,
            base_name=base_name,
            user_telegram_id=user.telegram_id,
            configs=config_items,
            total_limit=total_gb,
            expires_at=expiry_date,
            is_active=True
        )
        await subscription.save()
        
        # Update user and order
        user.subscriptions.append(subscription)
        await user.save()
        
        order.panel_configs = [subscription]
        order.expires_at = expiry_date
        await order.save()
        
        return {
            "subscription_url": f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{subscription_token}",
            "individual_configs": all_config_urls,
            "total_configs": len(all_config_urls)
        }
    
    def generate_config_url_from_item(self, config_item, inbound_config: dict, panel_ip: str) -> str:
        """Auto-generate config URL from ConfigItem"""
        try:
            return AutoConfigGenerator.generate(
                config_item.client_uuid,
                config_item.client_email, 
                inbound_config,
                panel_ip
            )
        except Exception as e:
            print(f"Error generating config URL: {e}")
            return None
    
    async def sync_subscription_to_new_panels(self, subscription: Subscription) -> Dict[str, Any]:
        """Sync existing subscription to newly enabled panels"""
        from app.models.subscription import ConfigItem
        
        # Get panels that already have configs
        existing_panels = set(config.panel_name for config in subscription.configs)
        
        # Find panels that need configs
        missing_panels = []
        for panel_name, panel_info in self.ENABLED_PANELS.items():
            if panel_info['name'] not in existing_panels:
                missing_panels.append((panel_name, panel_info))
        
        if not missing_panels:
            return {"added_configs": 0}
        
        print(f"🔄 Syncing subscription {subscription.base_name} to {len(missing_panels)} new panels")
        
        # Create configs for missing panels
        new_config_items = []
        
        for panel_name, panel_info in missing_panels:
            panel_service = XUIService(panel_name)
            inbounds_response = await panel_service.get_inbounds()
            
            if not inbounds_response or not inbounds_response.get("success"):
                continue
            
            existing_inbounds = inbounds_response.get("obj", [])
            
            for inbound_data in existing_inbounds:
                if not inbound_data.get("enable", True):
                    continue
                
                inbound_id = inbound_data["id"]
                client_id = str(uuid.uuid4())
                client_email = f"{subscription.base_name}_inbound{inbound_id}"
                
                # Add client with same limits/expiry as subscription
                expiry_timestamp = int(subscription.expires_at.timestamp() * 1000) if subscription.expires_at else 0
                
                result = await panel_service.add_client(
                    inbound_id=inbound_id,
                    client_email=client_email,
                    client_id=client_id,
                    total_gb=subscription.total_limit,
                    expire_time=expiry_timestamp
                )
                
                if result and result.get("success"):
                    protocol = inbound_data.get("protocol", "vless")
                    stored_id = client_id[:10] if protocol == "trojan" else client_id
                    
                    config_item = ConfigItem(
                        panel_name=panel_info['name'],
                        inbound_id=inbound_id,
                        client_uuid=stored_id,
                        client_email=client_email,
                        client_password=client_id[:10] if protocol == "trojan" else None
                    )
                    new_config_items.append(config_item)
                    print(f"✅ Added config for {panel_info['name']} inbound {inbound_id}")
        
        # Update subscription with new configs
        if new_config_items:
            subscription.configs.extend(new_config_items)
            await subscription.save()
            print(f"✅ Synced {len(new_config_items)} new configs to subscription")
        
        return {"added_configs": len(new_config_items)}
    
    async def create_vpn_config(self, order: Order, inbound_id: int = None, panel_name: str = "germany", config_type: str = "direct") -> Optional[str]:
        """Legacy method for backward compatibility"""
        result = await self.create_multi_panel_config(order)
        return result["individual_configs"][0] if result["individual_configs"] else None
    
    async def delete_vpn_config(self, order: Order) -> bool:
        """Delete VPN configuration from all panels"""
        subscription = await order.panel_configs[0].fetch() if order.panel_configs else None
        if not subscription:
            return False
        
        deleted_count = 0
        for config_item in subscription.configs:
            try:
                panel_service = XUIService(config_item.panel_name.lower())
                success = await panel_service.delete_client(config_item.inbound_id, config_item.client_uuid)
                if success:
                    deleted_count += 1
            except Exception as e:
                print(f"Error deleting from {config_item.panel_name}: {e}")
        
        subscription.is_active = False
        await subscription.save()
        return deleted_count > 0
    
    async def get_user_configs(self, subscription_token: str) -> List[str]:
        """Get all config URLs for a subscription by token"""
        subscription = await Subscription.find_one(Subscription.subscription_token == subscription_token)
        if not subscription or not subscription.is_active:
            return []
        
        all_configs = []
        for config_item in subscription.configs:
            panel_info = None
            for panel_name, info in self.ENABLED_PANELS.items():
                if info['name'] == config_item.panel_name:
                    panel_info = info
                    break
            
            if not panel_info:
                continue
            
            try:
                panel_service = XUIService(panel_name)
                inbounds_response = await panel_service.get_inbounds()
                if inbounds_response and inbounds_response.get("success"):
                    existing_inbounds = inbounds_response.get("obj", [])
                    for inbound_data in existing_inbounds:
                        if inbound_data["id"] == config_item.inbound_id:
                            config_url = self.generate_config_url_from_item(config_item, inbound_data, panel_info['ip'])
                            if config_url:
                                all_configs.append(config_url)
                            break
            except Exception as e:
                print(f"Error getting config for {config_item.panel_name}: {e}")
        
        return all_configs


vpn_service = VPNService()