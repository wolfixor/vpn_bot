#!/usr/bin/env python3
"""
User Migration Script
Command-line tool for migrating users between VPN panels
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.migration_service import MigrationService
from app.core.logger import logger


async def migrate_single_subscription(token: str, target: str, reset_traffic: bool = True):
    """Migrate a single subscription"""
    from app.services.migration_service import migration_service
    from app.models.subscription import Subscription
    
    print(f"Migrating subscription {token[:8]}... to {target}...")
    
    subscription = await Subscription.find_one(Subscription.subscription_token == token)
    if not subscription:
        print(f"✗ Failed: Subscription not found")
        return False
    
    result = await migration_service.migrate_subscription(subscription, target, reset_traffic)
    
    if result["success"]:
        print(f"✓ Success: {result['message']}")
        print(f"  New configs: {result['new_configs_count']}")
        print(f"  Traffic preserved: {result['traffic_preserved']}")
    else:
        print(f"✗ Failed: {result['error']}")
    
    return result["success"]


async def migrate_bulk_subscriptions(tokens: list, target: str, reset_traffic: bool = True):
    """Migrate multiple subscriptions"""
    from app.services.migration_service import migration_service
    
    print(f"Migrating {len(tokens)} subscriptions to {target}...")
    result = await migration_service.bulk_migrate_subscriptions(tokens, target, reset_traffic)
    
    print(f"✓ Migrated: {result['migrated']}")
    print(f"✗ Failed: {result['failed']}")
    
    if result["details"]["failed"]:
        print("\nFailed migrations:")
        for failure in result["details"]["failed"]:
            print(f"  Token {failure['token'][:8]}...: {failure['error']}")


async def auto_balance():
    """Auto-balance subscriptions across panels"""
    from app.services.migration_service import migration_service
    
    print("Auto-balancing subscriptions across panels...")
    result = await migration_service.auto_balance_panels()
    
    if result["success"]:
        print(f"✓ {result['message']}")
        if "migrations" in result:
            print(f"  Performed {result['migrations']} migrations")
    else:
        print(f"✗ Failed: {result['error']}")


async def show_stats():
    """Show migration statistics"""
    from app.services.migration_service import migration_service
    
    result = await migration_service.get_migration_stats()
    
    if result["success"]:
        print("Panel Distribution:")
        for panel in result["panel_distribution"]:
            flag = panel.get('flag', '🌐')
            print(f"  {flag} {panel['panel_name']} ({panel['panel_key']}): {panel['count']} subscriptions")
        
        print(f"\nTotal Subscriptions: {result['total_subscriptions']}")
        print(f"Enabled Panels: {result['enabled_panels']}")
    else:
        print(f"✗ Failed to get stats: {result['error']}")


def main():
    parser = argparse.ArgumentParser(description="VPN Bot User Migration Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Single subscription migration
    migrate_parser = subparsers.add_parser("migrate", help="Migrate a single subscription")
    migrate_parser.add_argument("subscription_token", help="Subscription token to migrate")
    migrate_parser.add_argument("target_panel_key", help="Target panel key")
    migrate_parser.add_argument("--reset-traffic", action="store_true", help="Reset traffic usage")
    
    # Bulk migration
    bulk_parser = subparsers.add_parser("bulk", help="Migrate multiple subscriptions")
    bulk_parser.add_argument("subscription_tokens", nargs="+", help="Subscription tokens to migrate")
    bulk_parser.add_argument("--target", required=True, help="Target panel key")
    bulk_parser.add_argument("--reset-traffic", action="store_true", help="Reset traffic usage")
    
    # Auto-balance
    subparsers.add_parser("balance", help="Auto-balance users across panels")
    
    # Statistics
    subparsers.add_parser("stats", help="Show migration statistics")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == "migrate":
            asyncio.run(migrate_single_subscription(args.subscription_token, args.target_panel_key, args.reset_traffic))
        elif args.command == "bulk":
            asyncio.run(migrate_bulk_subscriptions(args.subscription_tokens, args.target, args.reset_traffic))
        elif args.command == "balance":
            asyncio.run(auto_balance())
        elif args.command == "stats":
            asyncio.run(show_stats())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Migration script error: {e}")


if __name__ == "__main__":
    main()