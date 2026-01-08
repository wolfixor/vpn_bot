import yaml
from pathlib import Path
from typing import Dict, Any

class PanelConfig:
    _config = None
    
    @classmethod
    def load(cls):
        if cls._config is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "panels.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config = yaml.safe_load(f)
        return cls._config
    
    @classmethod
    def get_enabled_panels(cls) -> Dict[str, Any]:
        config = cls.load()
        return {k: v for k, v in config['panels'].items() if v.get('enabled', False)}
    
    @classmethod
    def get_panel(cls, panel_name: str) -> Dict[str, Any]:
        config = cls.load()
        return config['panels'].get(panel_name)
    
    @classmethod
    def is_tunnel_ip(cls, ip: str) -> bool:
        config = cls.load()
        tunnel_ips = config.get('tunnel_ips', [])
        is_tunnel = ip in tunnel_ips
        print(f"🔍 Checking IP {ip} against tunnel_ips {tunnel_ips}: {is_tunnel}")
        return is_tunnel
    
    @classmethod
    def get_panel_by_name(cls, name: str) -> tuple:
        """Get panel key and info by panel name"""
        config = cls.load()
        for key, panel in config['panels'].items():
            if panel['name'].lower() == name.lower():
                return key, panel
        return None, None
    
    @classmethod
    def get_max_panels_per_user(cls) -> int:
        """Get max panels per user from settings"""
        config = cls.load()
        return config.get('settings', {}).get('max_panels_per_user', 1)
    
    @classmethod
    def get_max_tunnels_per_panel(cls) -> int:
        """Get max tunnels per panel from settings (0 = all tunnels)"""
        config = cls.load()
        return config.get('settings', {}).get('max_tunnels_per_panel', 1)
    
    @classmethod
    def is_auto_recovery_enabled(cls) -> bool:
        """Check if automatic disaster recovery is enabled"""
        config = cls.load()
        return config.get('settings', {}).get('auto_recovery_enabled', True)
    
    @classmethod
    def get_health_check_interval(cls) -> int:
        """Get health check interval in seconds"""
        config = cls.load()
        return config.get('settings', {}).get('health_check_interval', 300)

panel_config = PanelConfig()
