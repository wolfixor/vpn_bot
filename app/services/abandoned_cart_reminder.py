"""Abandoned cart reminder service"""
import asyncio
from datetime import datetime, timedelta
from app.models.payment import Payment
from app.models.order import Order
from app.models.vpn_plan import VPNPlan
from app.core.config import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def check_abandoned_carts(bot):
    """Check for abandoned carts and send reminder after 30 minutes"""
    while True:
        try:
            # Check every 10 minutes
            await asyncio.sleep(600)
            
            # Find payments created 30 minutes ago without proof
            thirty_min_ago = datetime.utcnow() - timedelta(minutes=30)
            
            abandoned_payments = await Payment.find({
                "status": "pending",
                "payment_proof_file_id": None,
                "created_at": {"$lte": thirty_min_ago},
                "reminder_sent": {"$ne": True}
            }).to_list()
            
            for payment in abandoned_payments:
                try:
                    # Get order and plan details
                    order = await Order.get(payment.order_id)
                    plan = await order.vpn_plan.fetch()
                    
                    # Calculate discount (30% off)
                    original_price = int(plan.price / 1000)
                    discounted_price = int(original_price * 0.7)
                    discount_percent = 30
                    
                    # Send reminder message
                    text = f"👋 سلام خوبید؟\n\n"
                    text += f"پشتیبان {settings.BOT_NAME} هستم، دیدم که میخواستید خرید کنید و تا مرحله فاکتور هم پیش رفتید، اما پرداخت نکردید.\n\n"
                    text += f"از اونجایی که اولین سفارشتون رو پیش ما دارید ثبت میکنید، تیم ما برای سرویس '{plan.name}' یک آفر {discount_percent} درصدی در نظر گرفته که شما میتونید تا یک ساعت آینده با پرداخت {discounted_price}تومان به جای {original_price}تومان این سرویس رو خریداری کنید.\n\n"
                    text += f"بازم اگه سوالی داشتی میتونی پی وی ({settings.SUPPORT_USERNAME}) بهم پیام بدی ❤️\n\n"
                    text += "⚡️برای خرید این سرویس گزینه پرداخت رو بزن:"
                    
                    keyboard = [
                        [InlineKeyboardButton("💳 پرداخت با تخفیف", callback_data=f"payment_{payment.payment_method}")],
                        [InlineKeyboardButton("❌ بیخیال", callback_data="back_to_main")]
                    ]
                    
                    await bot.send_message(
                        chat_id=payment.user_telegram_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                    # Mark reminder as sent
                    payment.reminder_sent = True
                    await payment.save()
                    
                    print(f"✅ Sent abandoned cart reminder to user {payment.user_telegram_id}")
                    
                except Exception as e:
                    print(f"❌ Error sending reminder to {payment.user_telegram_id}: {e}")
                
                # Small delay between messages
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ Error in abandoned cart checker: {e}")
            await asyncio.sleep(60)
