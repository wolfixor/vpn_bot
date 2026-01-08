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
from app.core.panel_config import panel_config

class VPNService:
    
    async def create_subscription(self, order: Order, config_name: str = None) -> Dict[str, Any]:
        """Create VPN configs on ALL enabled panels - user gets unlimited configs but limited traffic estimation"""
        from app.models.subscription import ConfigItem
        from app.services.load_balancer import load_balancer
        
        user = await order.user.fetch() if hasattr(order.user, 'fetch') else order.user
        vpn_plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
        
        subscription_token = str(uuid.uuid4())
        expiry_date = datetime.utcnow() + timedelta(days=vpn_plan.duration_days)
        expiry_timestamp = int(expiry_date.timestamp() * 1000)
        
        # Handle unlimited vs limited plans properly
        if vpn_plan.traffic_limit_gb is None:
            # Unlimited plan: set limit in panel, show unlimited to user
            if vpn_plan.duration_days <= 30:
                estimated_gb = 200 * 1024 * 1024 * 1024  # 1 month = 200GB
            elif vpn_plan.duration_days <= 60:
                estimated_gb = 400 * 1024 * 1024 * 1024  # 2 months = 400GB
            else:
                estimated_gb = 800 * 1024 * 1024 * 1024  # 3 months = 800GB
            display_traffic = None  # Show as unlimited to user
            actual_limit = estimated_gb  # Set limit in panel
        else:
            # Limited plan: user sees actual limit
            estimated_gb = vpn_plan.traffic_limit_gb * 1024 * 1024 * 1024
            display_traffic = vpn_plan.traffic_limit_gb
            actual_limit = estimated_gb
        
        base_uuid = str(uuid.uuid4())
        base_name = f"{config_name}_{base_uuid[:8]}" if config_name else f"user_{user.telegram_id}_{base_uuid[:8]}"
        print(f"🏷️ Config name provided: '{config_name}' -> Base name: '{base_name}'")
        
        config_items = []
        all_config_urls = []
        
        # Get ALL enabled panels from config
        enabled_panels = panel_config.get_enabled_panels()
        
        # MULTI-PANEL MODE: Read max panels per user from config
        MAX_PANELS_PER_USER = panel_config.get_max_panels_per_user()
        print(f"📋 Max panels per user: {MAX_PANELS_PER_USER}")
        
        from app.services.load_balancer import load_balancer
        await load_balancer.sync_server_loads()
        
        # Get servers sorted by load (lowest first)
        from app.models.server_load import ServerLoad
        enabled_names = [info['name'] for info in enabled_panels.values()]
        servers = await ServerLoad.find(
            {"is_active": True, "panel_name": {"$in": enabled_names}}
        ).sort(+ServerLoad.current_subscriptions).to_list()
        
        # Select top N panels with capacity
        selected_panels = []
        for server in servers:
            if len(selected_panels) >= MAX_PANELS_PER_USER:
                break
            # Find panel key from server name
            for key, info in enabled_panels.items():
                if info['name'] == server.panel_name:
                    selected_panels.append((key, info))
                    break
        
        # Fallback if not enough servers in DB
        if len(selected_panels) < MAX_PANELS_PER_USER:
            for key, info in enabled_panels.items():
                if len(selected_panels) >= MAX_PANELS_PER_USER:
                    break
                if not any(p[0] == key for p in selected_panels):
                    selected_panels.append((key, info))
        
        print(f"🎯 Selected {len(selected_panels)} panels for user: {[p[1]['name'] for p in selected_panels]}")
        
        # Create configs on SELECTED panels (multi-panel load balancing)
        for selected_panel_name, selected_panel_info in selected_panels:
            panel_service = XUIService(selected_panel_name)
            
            # Get ALL direct + 1 tunnel inbound from each selected panel
            from app.services.inbound_balancer import inbound_balancer
            
            selected_inbounds = await inbound_balancer.get_balanced_inbounds(selected_panel_name)
        
            for inbound_info in selected_inbounds:
                inbound_data = inbound_info["data"]
                inbound_id = inbound_data["id"]
                client_id = str(uuid.uuid4())
                
                # Better naming: location + type (direct/tunnel)
                inbound_type = "tunnel" if inbound_info["is_tunnel"] else "direct"
                panel_location = selected_panel_info['name'].lower().replace(' ', '_')
                
                # For internal tracking (full name with base_name and inbound_id for uniqueness)
                client_email = f"{base_name}_{selected_panel_name}_inbound{inbound_id}"
                
                # For display in VPN app (just location + type)
                display_name = f"{panel_location}_{inbound_type}"
                
                print(f"📧 Creating client: {client_email} (display: {display_name}, inbound {inbound_id})")
                
                result = await panel_service.add_client(
                    inbound_id=inbound_id,
                    client_email=client_email,
                    client_id=client_id,
                    total_gb=actual_limit,
                    expire_time=expiry_timestamp
                )
                
                if result and result.get("success"):
                    protocol = inbound_data.get("protocol", "vless")
                    stored_id = client_id[:10] if protocol == "trojan" else client_id
                    
                    config_item = ConfigItem(
                        panel_name=selected_panel_info['name'],
                        inbound_id=inbound_id,
                        client_uuid=stored_id,
                        client_email=client_email,
                        client_password=client_id[:10] if protocol == "trojan" else None
                    )
                    config_items.append(config_item)
                    
                    # Generate config with display name instead of full client_email
                    config_url = self.generate_config_url_from_item(config_item, inbound_data, inbound_info["ip"], display_name)
                    if config_url:
                        all_config_urls.append({"config": config_url, "panel_flag": selected_panel_info['flag']})
                    
                    inbound_type = "tunnel" if inbound_info["is_tunnel"] else "direct"
                    print(f"✅ Added to {selected_panel_info['name']} inbound {inbound_id} ({inbound_type}) - {inbound_info['client_count']} existing clients")
            
            # Track subscription on each selected panel
            await load_balancer.allocate_subscription_to_server(selected_panel_name)
        
        subscription = Subscription(
            subscription_token=subscription_token,
            base_name=base_name,
            user_telegram_id=user.telegram_id,
            configs=config_items,
            total_limit=estimated_gb,  # Use estimated for monitoring
            expires_at=expiry_date,
            is_active=True
        )
        await subscription.save()
        
        user.subscriptions.append(subscription)
        await user.save()
        
        order.panel_configs = [subscription]
        order.expires_at = expiry_date
        await order.save()
        
        subscription_url = f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{subscription_token}"
        
        return {
            "subscription_url": subscription_url,
            "individual_configs": all_config_urls,
            "total_configs": len(all_config_urls),
            "display_traffic": display_traffic
        }
    
    async def _send_capacity_alert(self, message: str):
        """Send capacity alert to admin"""
        try:
            from app.bot.bot import bot
            admin_ids = settings.BOT_ADMIN_IDS.split(',')
            for admin_id in admin_ids:
                await bot.application.bot.send_message(
                    chat_id=int(admin_id.strip()),
                    text=f"🚨 **Server Capacity Alert**\n\n{message}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"Failed to send capacity alert: {e}")
    
    def get_inbound_ip(self, inbound_data: dict) -> str:
        """Extract IP from inbound configuration"""
        try:
            # Check stream settings for IP
            stream_settings = json.loads(inbound_data.get('streamSettings', '{}'))
            
            # Check external proxy settings (tunnel configs)
            if 'externalProxy' in stream_settings:
                proxy_list = stream_settings['externalProxy']
                if proxy_list and len(proxy_list) > 0:
                    proxy = proxy_list[0]
                    dest = proxy.get('dest', '')
                    if dest:
                        return dest.split(':')[0] if ':' in dest else dest
            
            # Check Reality settings
            if 'realitySettings' in stream_settings:
                dest = stream_settings['realitySettings'].get('dest', '')
                if ':' in dest:
                    return dest.split(':')[0]
            
            # Check listen field
            listen = inbound_data.get('listen', '')
            if listen and listen != '0.0.0.0':
                return listen
                
            return ''
        except:
            return ''
    
    def generate_config_url_from_item(self, config_item, inbound_config: dict, panel_ip: str, display_name: str = None) -> str:
        """Auto-generate config URL from ConfigItem"""
        try:
            return AutoConfigGenerator.generate(
                config_item.client_uuid,
                display_name or config_item.client_email,
                inbound_config,
                panel_ip
            )
        except Exception as e:
            print(f"Error generating config URL: {e}")
            return None
    

    
    async def delete_subscription(self, subscription: Subscription) -> bool:
        """Delete subscription from all panels"""
        from app.services.load_balancer import load_balancer
        
        deleted_count = 0
        for config_item in subscription.configs:
            try:
                panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
                if not panel_key:
                    continue
                
                panel_service = XUIService(panel_key)
                success = await panel_service.delete_client(config_item.inbound_id, config_item.client_uuid)
                if success:
                    deleted_count += 1
            except Exception as e:
                print(f"Error deleting from {config_item.panel_name}: {e}")
        
        subscription.is_active = False
        await subscription.save()
        
        # Deallocate from load balancer
        for config_item in subscription.configs:
            panel_key, _ = panel_config.get_panel_by_name(config_item.panel_name)
            if panel_key:
                await load_balancer.deallocate_subscription_from_server(panel_key)
        
        return deleted_count > 0
    
    async def sync_subscription_to_new_panels(self, subscription: Subscription) -> bool:
        """Sync existing subscription to newly enabled panels (no-op for single-panel system)"""
        # In the new flow, each subscription is on ONE panel only
        # This method is kept for compatibility but does nothing
        return True
    
    async def get_user_configs(self, subscription_token: str) -> List[str]:
        """Get all config URLs for a subscription by token - fully dynamic"""
        subscription = await Subscription.find_one(Subscription.subscription_token == subscription_token)
        if not subscription or not subscription.is_active:
            return []
        
        all_configs = []
        
        for config_item in subscription.configs:
            # Find panel dynamically by name
            panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
            
            if not panel_key or not panel_info or not panel_info.get('enabled'):
                continue
            
            try:
                panel_service = XUIService(panel_key)
                inbounds_response = await panel_service.get_inbounds()
                if inbounds_response and inbounds_response.get("success"):
                    for inbound_data in inbounds_response.get("obj", []):
                        if inbound_data["id"] == config_item.inbound_id:
                            # Detect tunnel vs direct dynamically
                            inbound_ip = self.get_inbound_ip(inbound_data)
                            is_tunnel = panel_config.is_tunnel_ip(inbound_ip)
                            config_ip = inbound_ip if is_tunnel else panel_info['direct_ip']
                            
                            config_url = self.generate_config_url_from_item(config_item, inbound_data, config_ip)
                            if config_url:
                                all_configs.append(config_url)
                            break
            except Exception as e:
                print(f"Error getting config for {config_item.panel_name}: {e}")
        
        return all_configs

vpn_service = VPNService()
