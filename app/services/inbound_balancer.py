from typing import Dict, List, Optional, Tuple
from app.core.panel_config import panel_config
from app.services.xui_service import XUIService
from app.models.subscription import Subscription
import json

class InboundBalancerService:
    """Handle inbound-level load balancing within panels"""
    
    async def get_balanced_inbounds(self, panel_key: str, max_inbounds: int = 10) -> List[Dict]:
        """Get ALL direct inbounds + balanced tunnel inbounds from a panel"""
        panel_service = XUIService(panel_key)
        panel_info = panel_config.get_panel(panel_key)
        
        if not panel_info:
            return []
        
        # Get all inbounds from panel
        inbounds_response = await panel_service.get_inbounds()
        if not inbounds_response or isinstance(inbounds_response, str) or not inbounds_response.get("success"):
            print(f"❌ Failed to get inbounds: {inbounds_response}")
            return []
        
        tunnel_inbounds = []
        direct_inbounds = []
        
        # Categorize inbounds by type
        for inbound_data in inbounds_response.get("obj", []):
            if not inbound_data.get("enable", True):
                continue
            
            inbound_ip = self._get_inbound_ip(inbound_data)
            is_tunnel = panel_config.is_tunnel_ip(inbound_ip)
            print(f"🔍 Inbound {inbound_data['id']}: IP={inbound_ip}, is_tunnel={is_tunnel}")
            
            # Get current client count for this inbound
            client_count = await self._get_inbound_client_count(panel_service, inbound_data["id"])
            
            inbound_info = {
                "id": inbound_data["id"],
                "data": inbound_data,
                "client_count": client_count,
                "is_tunnel": is_tunnel,
                "ip": inbound_ip if is_tunnel else panel_info['direct_ip']
            }
            
            if is_tunnel:
                tunnel_inbounds.append(inbound_info)
            else:
                direct_inbounds.append(inbound_info)
        
        # Sort tunnels by client count (least loaded first)
        tunnel_inbounds.sort(key=lambda x: x["client_count"])
        
        selected_inbounds = []
        
        # Strategy: Give user ALL direct inbounds + N least loaded tunnels
        # Add ALL direct inbounds
        selected_inbounds.extend(direct_inbounds)
        
        # Add N least loaded tunnel inbounds (0 = all tunnels)
        max_tunnels = panel_config.get_max_tunnels_per_panel()
        if max_tunnels == 0:
            # 0 means ALL tunnels
            selected_inbounds.extend(tunnel_inbounds)
            tunnel_count = len(tunnel_inbounds)
        else:
            # Add only N least loaded tunnels
            selected_inbounds.extend(tunnel_inbounds[:max_tunnels])
            tunnel_count = min(max_tunnels, len(tunnel_inbounds))
        
        print(f"🎯 Selected {len(selected_inbounds)} inbounds from {panel_info['name']}")
        direct_count = len(direct_inbounds)
        print(f"  • Direct inbounds: {direct_count} (ALL)")
        print(f"  • Tunnel inbounds: {tunnel_count} {'(ALL)' if max_tunnels == 0 else f'(top {max_tunnels})'}")
        
        for inbound in selected_inbounds:
            inbound_type = "tunnel" if inbound["is_tunnel"] else "direct"
            print(f"  • Inbound {inbound['id']}: {inbound['client_count']} clients ({inbound_type})")
        
        return selected_inbounds
    
    async def _get_inbound_client_count(self, panel_service: XUIService, inbound_id: int) -> int:
        """Get current client count for an inbound"""
        try:
            clients_response = await panel_service.get_clients(inbound_id)
            if clients_response and clients_response.get("success"):
                clients = clients_response.get("obj", [])
                return len([c for c in clients if c.get("enable", True)])
            return 0
        except:
            return 0
    
    def _get_inbound_ip(self, inbound_data: dict) -> str:
        """Extract IP from inbound configuration"""
        try:
            inbound_id = inbound_data.get('id', 'unknown')
            
            # Check stream settings for IP
            stream_settings_str = inbound_data.get('streamSettings', '{}')
            stream_settings = json.loads(stream_settings_str)
            
            # Check Reality settings for destination IP
            if 'realitySettings' in stream_settings:
                reality = stream_settings['realitySettings']
                dest = reality.get('dest', '')
                if ':' in dest:
                    ip = dest.split(':')[0]
                    print(f"🔍 Inbound {inbound_id}: Found Reality dest IP: {ip}")
                    return ip
            
            # Check external proxy settings (common for tunnel configs)
            if 'externalProxy' in stream_settings:
                proxy_list = stream_settings['externalProxy']
                if proxy_list and len(proxy_list) > 0:
                    proxy = proxy_list[0]
                    dest = proxy.get('dest', '')
                    if dest:
                        ip = dest.split(':')[0] if ':' in dest else dest
                        print(f"🔍 Inbound {inbound_id}: Found external proxy IP: {ip}")
                        return ip
                else:
                    print(f"🔍 Inbound {inbound_id}: External proxy array is empty")
            
            # Check listen field
            listen = inbound_data.get('listen', '')
            if listen and listen != '0.0.0.0' and listen != '':
                print(f"🔍 Inbound {inbound_id}: Found listen IP: {listen}")
                return listen
            
            # Check settings for any IP references
            settings_str = inbound_data.get('settings', '{}')
            if settings_str:
                settings = json.loads(settings_str)
                # Look for any IP patterns in settings
                settings_json = json.dumps(settings)
                import re
                ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                ips = re.findall(ip_pattern, settings_json)
                if ips:
                    ip = ips[0]
                    print(f"🔍 Inbound {inbound_id}: Found IP in settings: {ip}")
                    return ip
            
            print(f"⚠️ Inbound {inbound_id}: No IP found in any field")
            print(f"    Stream settings keys: {list(stream_settings.keys())}")
            if 'externalProxy' in stream_settings:
                print(f"    External proxy: {stream_settings['externalProxy']}")
            return ''
            
        except Exception as e:
            print(f"❌ Error extracting IP from inbound {inbound_data.get('id', 'unknown')}: {e}")
            return ''
    
    async def get_inbound_load_stats(self, panel_key: str) -> Dict:
        """Get detailed load statistics for all inbounds in a panel"""
        panel_service = XUIService(panel_key)
        panel_info = panel_config.get_panel(panel_key)
        
        if not panel_info:
            return {}
        
        inbounds_response = await panel_service.get_inbounds()
        if not inbounds_response or not inbounds_response.get("success"):
            return {}
        
        stats = {
            "panel_name": panel_info['name'],
            "tunnel_inbounds": [],
            "direct_inbounds": [],
            "total_clients": 0
        }
        
        for inbound_data in inbounds_response.get("obj", []):
            if not inbound_data.get("enable", True):
                continue
            
            inbound_ip = self._get_inbound_ip(inbound_data)
            is_tunnel = panel_config.is_tunnel_ip(inbound_ip)
            client_count = await self._get_inbound_client_count(panel_service, inbound_data["id"])
            
            inbound_stats = {
                "id": inbound_data["id"],
                "protocol": inbound_data.get("protocol", "unknown"),
                "port": inbound_data.get("port", 0),
                "client_count": client_count,
                "ip": inbound_ip
            }
            
            if is_tunnel:
                stats["tunnel_inbounds"].append(inbound_stats)
            else:
                stats["direct_inbounds"].append(inbound_stats)
            
            stats["total_clients"] += client_count
        
        return stats

inbound_balancer = InboundBalancerService()