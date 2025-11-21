import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.models.payment import Payment
from app.models.order import Order
from app.models.user import User
from app.core.config import settings

class PaymentService:
    
    # Payment methods configuration
    PAYMENT_METHODS = {
        "card_to_card": {
            "name": "💳 کارت به کارت",
            "address": settings.CARD_NUMBER,
            "holder": settings.NAME_CARD,
        },
        "crypto": {
            "name": "₿ ارز دیجیتال",
            "Tether_address": settings.TETHER,
            "Tron_address": settings.TRON,
            "Solana_address": settings.SOLANA
        }
    }
    
    async def create_payment_request(self, order: Order, payment_method: str, user_telegram_id: int) -> Payment:
        """Create payment request for order"""
        payment = Payment(
            order_id=str(order.id),
            user_telegram_id=user_telegram_id,
            payment_method=payment_method,
            amount=order.price,
            currency="USD",
            status="pending",
            expires_at=datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
        )
        await payment.save()
        
        # Update order status
        from app.models.order import OrderStatus
        order.status = OrderStatus.PAYMENT_PENDING
        await order.save()
        
        return payment
    
    def get_payment_instructions(self, payment: Payment) -> str:
        """Get payment instructions text"""
        print(f"🔍 Original payment method: '{payment.payment_method}'")
        
        # Normalize payment method (remove 'payment_' prefix if exists)
        normalized_method = payment.payment_method.replace("payment_", "")
        print(f"🔍 Normalized method: '{normalized_method}'")
        print(f"🔍 Available methods: {list(self.PAYMENT_METHODS.keys())}")
        
        method_info = self.PAYMENT_METHODS.get(normalized_method)
        print(f"🔍 Method info found: {method_info is not None}")
        
        if not method_info:
            print(f"❌ Method '{normalized_method}' not found in PAYMENT_METHODS")
            return f"❌ **روش پرداخت نامعتبر**\n\nلطفاً با پشتیبانی تماس بگیرید."
        
        text = ""
        
        if normalized_method == "card_to_card":
            text = f"💳 **پرداخت کارت به کارت**\n\n"
            amount_display = int(payment.amount / 1000)
            text += f"💰 **مبلغ:** {amount_display}تومان\n"
            text += f"💳 **شماره کارت:** `{method_info['address']}`\n"
            text += f"👤 **صاحب حساب:** {method_info['holder']}\n\n"
            text += "📋 **مراحل پرداخت:**\n"
            text += "1. مبلغ را به شماره کارت بالا واریز کنید\n"
            text += "2. عکس رسید واریز را ارسال کنید\n"
            text += "3. منتظر تأیید ادمین باشید (حداکثر 2 ساعت)\n"
            text += "4. پس از تأیید، کانفیگ VPN ارسال می‌شود\n\n"
            text += "⏰ **مهلت پرداخت:** 1 ساعت"
            
        elif normalized_method == "crypto":
            text = f"₿ **پرداخت ارز دیجیتال**\n\n"
            amount_display = int(payment.amount / 1000)
            text += f"💰 **مبلغ:** {amount_display}تومان\n\n"
            text += "📍 **آدرس‌های پرداخت:**\n"
            text += f"**USDT (TRC20):**\n`{method_info['Tether_address']}`\n\n"
            text += f"**TRON:**\n`{method_info['Tron_address']}`\n\n"
            text += f"**SOLANA:**\n`{method_info['Solana_address']}`\n\n"
            text += "📋 **مراحل پرداخت:**\n"
            text += "1. مبلغ معادل را به یکی از آدرس‌های بالا ارسال کنید\n"
            text += "2. عکس تراکنش (Transaction Hash) را ارسال کنید\n"
            text += "3. منتظر تأیید ادمین باشید (حداکثر 2 ساعت)\n"
            text += "4. پس از تأیید، کانفیگ VPN ارسال می‌شود\n\n"
            text += "⏰ **مهلت پرداخت:** 1 ساعت"
        else:
            text = f"❌ **روش پرداخت نامعتبر**\n\nلطفاً با پشتیبانی تماس بگیرید."
        
        return text
    
    async def submit_payment_proof(self, payment: Payment, photo_file_id: str, message: str = None) -> bool:
        """Submit payment proof photo"""
        payment.proof_photo_file_id = photo_file_id
        payment.proof_message = message
        payment.status = "proof_submitted"
        await payment.save()
        return True
    
    async def confirm_payment(self, payment: Payment, admin_id: int) -> bool:
        """Confirm payment by admin"""
        payment.status = "confirmed"
        payment.confirmed_by = admin_id
        payment.confirmed_at = datetime.utcnow()
        await payment.save()
        
        # Update order status
        from app.models.order import OrderStatus
        order = await Order.get(payment.order_id)
        order.status = OrderStatus.PAID
        await order.save()
        
        return True
    
    async def reject_payment(self, payment: Payment, admin_id: int) -> bool:
        """Reject payment by admin"""
        payment.status = "rejected"
        payment.confirmed_by = admin_id
        payment.confirmed_at = datetime.utcnow()
        await payment.save()
        
        # Update order status
        from app.models.order import OrderStatus
        order = await Order.get(payment.order_id)
        order.status = OrderStatus.CANCELLED
        await order.save()
        
        return True

payment_service = PaymentService()