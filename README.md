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

- Users get configs from ALL enabled panels
- Unlimited traffic plans with estimation
- Dynamic panel management via YAML
- Automatic tunnel/direct detection
- Never stops creating users
- Background monitoring and cleanup
- **Coupon system** with detailed tracking (see [COUPON_SYSTEM.md](COUPON_SYSTEM.md))
- Order ID support for customer service
- Auto-balance and migration system