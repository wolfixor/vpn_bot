# VPN Bot

Dynamic multi-panel VPN selling bot with unlimited configs.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure panels in `config/panels.yaml`

3. Set environment variables in `.env`

4. Run:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Features

- **Smart Load Balancing**: Users get configs from ONE selected panel (optimal performance)
- **Migration System**: Move users between panels seamlessly
- **Auto-Balance**: Automatically distribute users across panels
- **Dynamic Panel Management**: Add/remove panels via YAML configuration
- **Unlimited Traffic Plans**: With intelligent estimation and monitoring
- **Automatic Tunnel/Direct Detection**: Smart config generation
- **Never Stops Creating Users**: Business continuity with capacity alerts
- **Background Monitoring**: Automated cleanup and health checks
- **Coupon System**: Complete discount code system with analytics (see [COUPON_SYSTEM.md](COUPON_SYSTEM.md))
- **Disaster Recovery**: Restore all users to new infrastructure
- **Order ID Support**: Customer service tools
- **Hidden API Documentation**: Secure `/asdfasdfasfdf/docs` path