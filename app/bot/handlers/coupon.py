from telegram import Update
from telegram.ext import ContextTypes
from app.models.coupon import Coupon

async def handle_coupon_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coupon code input"""
    coupon_code = update.message.text.strip().upper()
    
    # Validate coupon
    coupon = await Coupon.find_one(Coupon.code == coupon_code)
    
    if not coupon:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("⏭️ بدون کد ادامه بده", callback_data="skip_coupon")]]
        await update.message.reply_text(
            "❌ **کد تخفیف نامعتبر**\n\n"
            "این کد تخفیف وجود ندارد.\n\n"
            "💡 کد دیگری امتحان کنید یا بدون کد ادامه دهید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    if not coupon.is_valid():
        reason = ""
        if not coupon.is_active:
            reason = "این کد تخفیف غیرفعال است."
        elif coupon.max_uses and coupon.current_uses >= coupon.max_uses:
            reason = "این کد تخفیف به حد مصرف رسیده است."
        else:
            reason = "این کد تخفیف منقضی شده است."
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("⏭️ بدون کد ادامه بده", callback_data="skip_coupon")]]
        await update.message.reply_text(
            f"❌ **کد تخفیف نامعتبر**\n\n{reason}\n\n"
            "💡 کد دیگری امتحان کنید یا بدون کد ادامه دهید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # Check plan restriction
    plan_id = context.user_data.get("selected_plan_id")
    if coupon.allowed_plans and plan_id not in coupon.allowed_plans:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [[InlineKeyboardButton("⏭️ بدون کد ادامه بده", callback_data="skip_coupon")]]
        await update.message.reply_text(
            "❌ **کد تخفیف نامعتبر**\n\n"
            "این کد تخفیف برای پلن انتخابی شما معتبر نیست.\n\n"
            "💡 کد دیگری امتحان کنید یا بدون کد ادامه دهید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # Save coupon to context
    context.user_data["coupon_code"] = coupon_code
    context.user_data["waiting_for_coupon"] = False
    
    # Calculate discount
    from app.models.vpn_plan import VPNPlan
    plan = await VPNPlan.get(plan_id)
    discount = coupon.calculate_discount(plan.price)
    final_price = plan.price - discount
    
    await update.message.reply_text(
        f"✅ **کد تخفیف اعمال شد!**\n\n"
        f"💰 قیمت اصلی: {int(plan.price / 1000):,} تومان\n"
        f"🎁 تخفیف: {int(discount / 1000):,} تومان\n"
        f"💵 قیمت نهایی: {int(final_price / 1000):,} تومان\n\n"
        "در حال انتقال به پرداخت...",
        parse_mode="Markdown"
    )
    
    # Show payment methods
    from app.bot.handlers.start import show_payment_methods
    await show_payment_methods(update)
