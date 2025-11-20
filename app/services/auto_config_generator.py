import json
from typing import Dict, Any

class AutoConfigGenerator:
    """Auto-generate config URLs for any protocol/transport/security combination"""
    
    @staticmethod
    def generate(client_id: str, client_email: str, inbound_data: dict, panel_ip: str) -> str:
        """Auto-detect and generate config URL from any inbound configuration"""
        try:
            # Parse inbound settings
            stream_settings = json.loads(inbound_data.get('streamSettings', '{}'))
            
            protocol = inbound_data['protocol']
            port = inbound_data['port']
            transport = stream_settings.get('network', 'tcp')
            security = stream_settings.get('security', 'none')
            
            # Auto-detect server address
            server_addr = panel_ip
            if stream_settings.get('externalProxy'):
                proxy = stream_settings['externalProxy'][0]
                server_addr = proxy['dest']
            
            # Generate config based on protocol
            if protocol == 'vless':
                return AutoConfigGenerator._generate_vless(
                    client_id, client_email, server_addr, port, 
                    transport, security, stream_settings
                )
            elif protocol == 'trojan':
                return AutoConfigGenerator._generate_trojan(
                    client_id, client_email, server_addr, port,
                    transport, security, stream_settings, inbound_data
                )
            elif protocol == 'vmess':
                return AutoConfigGenerator._generate_vmess(
                    client_id, client_email, server_addr, port,
                    transport, security, stream_settings
                )
            elif protocol == 'shadowsocks':
                return AutoConfigGenerator._generate_shadowsocks(
                    client_id, client_email, server_addr, port, inbound_data
                )
            else:
                # Generic fallback for any new protocol
                return f"{protocol}://{client_id}@{server_addr}:{port}#{client_email}"
                
        except Exception as e:
            print(f"Auto config generation error: {e}")
            return None
    
    @staticmethod
    def _generate_vless(client_id: str, client_email: str, server_addr: str, 
                       port: int, transport: str, security: str, stream_settings: dict) -> str:
        """Generate VLESS config for any transport/security combination"""
        base = f"vless://{client_id}@{server_addr}:{port}"
        params = []
        
        # Start with type and encryption
        params.extend(["type=" + transport, "encryption=none"])
        
        # Add transport-specific params first (path, host for WS; serviceName, authority for gRPC)
        if transport == 'ws':
            ws = stream_settings.get('wsSettings', {})
            ws_path = ws.get('path', '/ws')
            ws_host = ws.get('host', server_addr)
            # URL encode the path
            if ws_path.startswith('/'):
                ws_path = '%2F' + ws_path[1:]
            params.extend([
                f"path={ws_path}",
                f"host={ws_host}"
            ])
        elif transport == 'grpc':
            grpc = stream_settings.get('grpcSettings', {})
            params.extend([
                f"serviceName={grpc.get('serviceName', '')}",
                "authority="
            ])
        
        # Then add security settings
        if security == 'reality':
            reality = stream_settings.get('realitySettings', {})
            # Extract public key from settings or directly from reality config
            public_key = reality.get('publicKey', '')
            if not public_key and reality.get('settings'):
                public_key = reality['settings'].get('publicKey', '')
            
            params.extend([
                f"security={security}",
                f"pbk={public_key}",
                "fp=chrome",
                f"sni={reality.get('serverNames', ['zula.ir'])[0]}",
                f"sid={reality.get('shortIds', [''])[0]}",
                "spx=%2F"
            ])
        elif security == 'tls':
            params.extend([
                f"security={security}",
                "fp=chrome"
            ])
            
            # Add ALPN before SNI for correct order
            tls = stream_settings.get('tlsSettings', {})
            if tls.get('alpn'):
                # Properly encode ALPN values
                alpn_encoded = '%2C'.join([alpn.replace('/', '%2F') for alpn in tls['alpn']])
                params.append(f"alpn={alpn_encoded}")
            
            # Add SNI last
            params.append(f"sni={tls.get('serverName', server_addr)}")
        
        return f"{base}?{'&'.join(params)}#{client_email}"
    
    @staticmethod
    def _generate_trojan(client_id: str, client_email: str, server_addr: str,
                        port: int, transport: str, security: str, stream_settings: dict, inbound_data: dict = None) -> str:
        """Generate Trojan config for any transport/security combination"""
        # Extract actual password from inbound settings for the specific client
        password = client_id  # fallback
        if inbound_data:
            try:
                settings = json.loads(inbound_data.get('settings', '{}'))
                clients = settings.get('clients', [])
                for client in clients:
                    if client.get('email') == client_email:
                        password = client.get('password', client_id)
                        break
            except:
                pass
        
        base = f"trojan://{password}@{server_addr}:{port}"
        params = [f"type={transport}"]
        
        # Auto-detect security
        if security == 'reality':
            reality = stream_settings.get('realitySettings', {})
            # Extract public key from settings or directly from reality config
            public_key = reality.get('publicKey', '')
            if not public_key and reality.get('settings'):
                public_key = reality['settings'].get('publicKey', '')
            
            params.extend([
                f"security={security}",
                f"pbk={public_key}",
                "fp=chrome",
                f"sni={reality.get('serverNames', ['zula.ir'])[0]}",
                f"sid={reality.get('shortIds', [''])[0]}",
                "spx=%2F"
            ])
        elif security == 'tls':
            params.append(f"security={security}")
            tls = stream_settings.get('tlsSettings', {})
            params.extend([
                "fp=chrome",
                f"sni={tls.get('serverName', server_addr)}"
            ])
        
        # Auto-detect transport (same as VLESS)
        if transport == 'ws':
            ws = stream_settings.get('wsSettings', {})
            params.extend([
                f"path={ws.get('path', '/ws')}",
                f"host={ws.get('host', server_addr)}"
            ])
        elif transport == 'grpc':
            grpc = stream_settings.get('grpcSettings', {})
            params.append(f"serviceName={grpc.get('serviceName', '')}")
        
        return f"{base}?{'&'.join(params)}#{client_email}"
    
    @staticmethod
    def _generate_vmess(client_id: str, client_email: str, server_addr: str,
                       port: int, transport: str, security: str, stream_settings: dict) -> str:
        """Generate VMess config"""
        # VMess uses different format - JSON based
        config = {
            "v": "2",
            "ps": client_email,
            "add": server_addr,
            "port": str(port),
            "id": client_id,
            "aid": "0",
            "scy": "auto",
            "net": transport,
            "type": "none",
            "host": "",
            "path": "",
            "tls": security,
            "sni": "",
            "alpn": ""
        }
        
        # Auto-detect transport settings
        if transport == 'ws':
            ws = stream_settings.get('wsSettings', {})
            config["path"] = ws.get('path', '/vmess')
            config["host"] = ws.get('host', server_addr)
        elif transport == 'grpc':
            grpc = stream_settings.get('grpcSettings', {})
            config["path"] = grpc.get('serviceName', '')
            config["type"] = "gun"
        
        if security == 'tls':
            tls = stream_settings.get('tlsSettings', {})
            config["sni"] = tls.get('serverName', server_addr)
            if tls.get('alpn'):
                config["alpn"] = ','.join(tls['alpn'])
        
        import base64
        return "vmess://" + base64.b64encode(json.dumps(config).encode()).decode()
    
    @staticmethod
    def _generate_shadowsocks(client_id: str, client_email: str, server_addr: str,
                             port: int, inbound_data: dict) -> str:
        """Generate Shadowsocks config"""
        # Shadowsocks format: ss://method:password@server:port#name
        try:
            settings = json.loads(inbound_data.get('settings', '{}'))
            method = settings.get('method', 'aes-256-gcm')
            password = settings.get('password', client_id)
        except:
            method = 'aes-256-gcm'
            password = client_id
        
        import base64
        auth = base64.b64encode(f"{method}:{password}".encode()).decode()
        return f"ss://{auth}@{server_addr}:{port}#{client_email}"