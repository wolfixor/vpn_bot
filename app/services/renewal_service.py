from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.models.subscription import Subscription
from app.models.order import Order
from app.models.vpn_plan import VPNPlan
from app.models.user import User
from app.services.xui_service import XUIService
from app.services.vpn_service import vpn_service
from app.core.config import settings


class RenewalService:
    """Handle subscription renewal and recharge"""
    
    async def extend_subscription(
        self, 
        subscription: Subscription, 
        plan: VPNPlan,
        order: Order
    ) -> Dict[str, Any]:
        """Extend existing subscription with new plan"""
        
        # Calculate new expiry date
        current_expiry = subscription.expires_at or datetime.utcnow()
        if current_expiry < datetime.utcnow():
            # If expired, start from now
            new_expiry = datetime.utcnow() + timedelta(days=plan.duration_days)
        else:
            # If active, add to existing time
            new_expiry = current_expiry + timedelta(days=plan.duration_days)
        
        # Calculate new traffic limit
        if plan.traffic_limit_gb is None:
            # Unlimited plan: recalculate based on total duration
            total_days = (new_expiry - datetime.utcnow()).days
            if total_days <= 30:
                new_total_limit = 200 * 1024 * 1024 * 1024
            elif total_days <= 60:
                new_total_limit = 400 * 1024 * 1024 * 1024
            else:
                new_total_limit = 800 * 1024 * 1024 * 1024
        else:
            # Limited plan: add traffic
            additional_traffic = plan.traffic_limit_gb * 1024 * 1024 * 1024
            new_total_limit = (subscription.total_limit or 0) + additional_traffic
        
        # Update all configs in all panels
        updated_configs = 0
        failed_configs = []
        
        for config_item in subscription.configs:
            try:
                from app.core.panel_config import panel_config
                
                # Find panel dynamically by name
                panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
                if not panel_key:
                    failed_configs.append(config_item.client_email)
                    continue
                
                panel_service = XUIService(panel_key)
                
                # Update client with new limits
                expiry_timestamp = int(new_expiry.timestamp() * 1000)
                
                result = await panel_service.update_client(
                    inbound_id=config_item.inbound_id,
                    client_email=config_item.client_email,
                    client_id=config_item.client_uuid,
                    total_gb=new_total_limit,
                    expire_time=expiry_timestamp
                )
                
                if result and result.get("success"):
                    updated_configs += 1
                else:
                    failed_configs.append(config_item.client_email)
                    
            except Exception as e:
                print(f"❌ Error updating config {config_item.client_email}: {e}")
                failed_configs.append(config_item.client_email)
        
        # Update subscription record
        subscription.expires_at = new_expiry
        subscription.total_limit = new_total_limit
        subscription.is_active = True
        await subscription.save()
        
        # Update order
        order.expires_at = new_expiry
        await order.save()
        
        return {
            "success": True,
            "updated_configs": updated_configs,
            "failed_configs": failed_configs,
            "new_expiry": new_expiry,
            "new_traffic_limit_gb": new_total_limit / (1024**3) if new_total_limit else 0,
            "subscription_url": f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{subscription.subscription_token}"
        }
    
    async def get_active_subscriptions(self, user: User) -> list[Subscription]:
        """Get user's active subscriptions"""
        active_subs = []
        
        for sub_link in user.subscriptions:
            subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
            if subscription and subscription.is_active:
                active_subs.append(subscription)
        
        return active_subs
    
    async def is_unlimited_subscription(self, subscription: Subscription) -> bool:
        """Check if subscription is unlimited by finding original plan"""
        try:
            orders = await Order.find().to_list()
            for order in orders:
                if hasattr(order, 'panel_configs') and order.panel_configs:
                    for pc in order.panel_configs:
                        pc_obj = await pc.fetch() if hasattr(pc, 'fetch') else pc
                        if pc_obj and pc_obj.id == subscription.id:
                            plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
                            if plan:
                                return plan.traffic_limit_gb is None
            return False
        except Exception as e:
            print(f"❌ Error checking unlimited status: {e}")
            return False
    
    async def check_renewal_eligibility(self, subscription: Subscription) -> Dict[str, Any]:
        """Check if subscription can be renewed"""
        now = datetime.utcnow()
        
        # Check if expired
        is_expired = subscription.expires_at and subscription.expires_at < now
        
        # Check days remaining
        days_remaining = 0
        if subscription.expires_at:
            days_remaining = max(0, (subscription.expires_at - now).days)
        
        # Check traffic remaining
        traffic_used_gb = (subscription.traffic_used or 0) / (1024**3)
        traffic_limit_gb = (subscription.total_limit or 0) / (1024**3)
        
        # Check if unlimited
        is_unlimited = await self.is_unlimited_subscription(subscription)
        traffic_remaining_gb = float('inf') if is_unlimited else max(0, traffic_limit_gb - traffic_used_gb)
        
        return {
            "can_renew": True,  # Always allow renewal
            "is_expired": is_expired,
            "days_remaining": days_remaining,
            "traffic_remaining_gb": traffic_remaining_gb,
            "traffic_used_gb": traffic_used_gb,
            "traffic_limit_gb": traffic_limit_gb
        }


renewal_service = RenewalService()
