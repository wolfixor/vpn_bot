import httpx
import json
from typing import Dict, Any, Optional
from app.core.config import settings

class XUIService:
    # Simple panel configuration
    PANEL_CONFIG = {
        "germany": {
            "url": "https://185.110.188.73:8585/40ddBvHqnvDfdbjB55",
            "ip": "185.110.188.73"
        },
        "turkey": {
            "url": "http://91.216.104.8:8585/X8KSu6hHzZeZMwp",
            "ip": "91.216.104.8"
        }
    }
    
    def __init__(self, panel_name: str = None):
        if not panel_name:
            raise ValueError("Panel name is required")
            
        panel_name = panel_name.lower()
        if panel_name not in self.PANEL_CONFIG:
            raise ValueError(f"Panel '{panel_name}' not found in configuration")
            
        panel_info = self.PANEL_CONFIG[panel_name]
        self.panel_name = panel_name
        self.base_url = panel_info["url"].rstrip('/')
        self.panel_ip = panel_info["ip"]
        
        # Get panel-specific credentials
        if panel_name == "germany":
            self.username = settings.GERMANY_PANEL_USERNAME
            self.password = settings.GERMANY_PANEL_PASSWORD
        elif panel_name == "turkey":
            self.username = settings.TURKEY_PANEL_USERNAME
            self.password = settings.TURKEY_PANEL_PASSWORD
        else:
            # Default credentials for unknown panels
            self.username = "admin"
            self.password = "password"
        
        self.session_cookie = None
    
    async def login(self) -> Optional[str]:
        """Login to 3x-ui panel and return session cookie"""
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                f"{self.base_url}/login",
                data={
                    "username": self.username,
                    "password": self.password
                }
            )
            if response.status_code == 200:
                if '3x-ui' in response.cookies:
                    cookie = response.cookies['3x-ui']
                    self.session_cookie = cookie
                    return cookie
                else:
                    print("Login failed: No session cookie received")
                    return None
            else:
                print(f"Login failed: HTTP {response.status_code}")
                return None
    
    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
        """Get all inbounds"""
        cookie = await self.login()
        if not cookie:
            return "failed to login"
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/panel/api/inbounds/list",
                    cookies={"3x-ui": cookie}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("success"):
                        return result
                    else:
                        return "1"
                else:
                    return "2"
                    
            except Exception as e:
                return "3"
    
    async def add_client(self, inbound_id: int, client_email: str, client_id: str, 
                        total_gb: int = 0, expire_time: int = 0) -> Optional[Dict[str, Any]]:
        """Add client to inbound"""
        cookie = await self.login()
        if not cookie:
            return None
        
        # Get inbound info to determine protocol
        inbounds_response = await self.get_inbounds()
        if not inbounds_response or not inbounds_response.get("success"):
            return None
            
        target_inbound = None
        for inbound in inbounds_response.get("obj", []):
            if inbound["id"] == inbound_id:
                target_inbound = inbound
                break
        
        if not target_inbound:
            return None
        
        protocol = target_inbound.get("protocol", "vless")
        
        # Create client data based on protocol
        if protocol == "trojan":
            settings_data = {
                "clients": [{
                    "password": client_id[:10],  # Use first 10 chars as password
                    "email": client_email,
                    "limitIp": 2,
                    "totalGB": total_gb,
                    "expiryTime": expire_time,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }]
            }
        else:
            # VLESS/VMess format
            settings_data = {
                "clients": [{
                    "id": client_id,
                    "flow": "",
                    "email": client_email,
                    "limitIp": 2,
                    "totalGB": total_gb,
                    "expiryTime": expire_time,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }]
            }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                f"{self.base_url}/panel/api/inbounds/addClient",
                data={
                    "id": inbound_id,
                    "settings": json.dumps(settings_data)
                },
                cookies={"3x-ui": cookie}
            )
            if response.status_code == 200:
                return response.json()
            return None
    
    async def update_client(self, inbound_id: int, client_email: str, client_id: str,
                           total_gb: int = 0, expire_time: int = 0) -> Optional[Dict[str, Any]]:
        """Update client settings (traffic limit and expiry)"""
        cookie = await self.login()
        if not cookie:
            return None
        
        # Get inbound to determine protocol
        inbounds_response = await self.get_inbounds()
        if not inbounds_response or not inbounds_response.get("success"):
            return None
        
        target_inbound = None
        for inbound in inbounds_response.get("obj", []):
            if inbound["id"] == inbound_id:
                target_inbound = inbound
                break
        
        if not target_inbound:
            return None
        
        protocol = target_inbound.get("protocol", "vless")
        
        # Create client data based on protocol
        if protocol == "trojan":
            settings_data = {
                "clients": [{
                    "password": client_id[:10],
                    "email": client_email,
                    "limitIp": 2,
                    "totalGB": total_gb,
                    "expiryTime": expire_time,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }]
            }
        else:
            settings_data = {
                "clients": [{
                    "id": client_id,
                    "flow": "",
                    "email": client_email,
                    "limitIp": 2,
                    "totalGB": total_gb,
                    "expiryTime": expire_time,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }]
            }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                f"{self.base_url}/panel/api/inbounds/updateClient/{client_id}",
                data={
                    "id": inbound_id,
                    "settings": json.dumps(settings_data)
                },
                cookies={"3x-ui": cookie}
            )
            if response.status_code == 200:
                return response.json()
            return None
    
    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        """Delete client from inbound"""
        cookie = await self.login()
        if not cookie:
            return False
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                f"{self.base_url}/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
                cookies={"3x-ui": cookie}
            )
            return response.status_code == 200
    
    async def get_client_traffic(self, client_email: str) -> Optional[Dict[str, Any]]:
        """Get client traffic statistics"""
        cookie = await self.login()
        if not cookie:
            return None
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(
                f"{self.base_url}/panel/api/inbounds/getClientTraffics/{client_email}",
                cookies={"3x-ui": cookie}
            )
            if response.status_code == 200:
                return response.json()
            return None
    
    async def get_client_stats(self, inbound_id: int, client_email: str) -> Optional[Dict]:
        """Get client traffic statistics (alias for get_client_traffic)"""
        result = await self.get_client_traffic(client_email)
        if result and result.get("success"):
            return result.get("obj", {})
        return None
    
    async def create_inbound(self, inbound_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new inbound"""
        cookie = await self.login()
        if not cookie:
            return None
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                f"{self.base_url}/panel/api/inbounds/add",
                json=inbound_data,
                cookies={"3x-ui": cookie}
            )
            if response.status_code == 200:
                return response.json()
            return None
    
    def parse_inbound_settings(self, inbound_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse 3x-ui inbound data to extract config details"""
        try:
            stream_settings = json.loads(inbound_data.get('streamSettings', '{}'))
            
            config = {
                'protocol': inbound_data['protocol'],
                'port': inbound_data['port'],
                'transport': stream_settings.get('network', 'tcp'),
                'security': stream_settings.get('security', 'none')
            }
            
            # Extract Reality settings
            if config['security'] == 'reality':
                reality = stream_settings.get('realitySettings', {})
                config['reality_public_key'] = reality.get('settings', {}).get('publicKey')
                config['reality_server_names'] = reality.get('serverNames', [])
                config['reality_short_ids'] = reality.get('shortIds', [])
            
            # Extract WebSocket settings
            if config['transport'] == 'ws':
                ws = stream_settings.get('wsSettings', {})
                config['ws_path'] = ws.get('path')
                config['ws_host'] = ws.get('host')
            
            # Extract gRPC settings
            if config['transport'] == 'grpc':
                grpc = stream_settings.get('grpcSettings', {})
                config['grpc_service'] = grpc.get('serviceName', '')
            
            # Extract tunnel info
            if stream_settings.get('externalProxy'):
                proxy = stream_settings['externalProxy'][0]
                config['tunnel_dest'] = proxy['dest']
                config['tunnel_port'] = proxy['port']
            
            return config
            
        except Exception as e:
            print(f"Error parsing inbound settings: {e}")
            return {}

# XUIService instances are created per panel as needed
# Example: germany_service = XUIService("germany")