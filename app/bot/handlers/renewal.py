from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.models.user import User
from app.models.vpn_plan import VPNPlan
from app.models.order import Order, OrderStatus
from app.models.subscription import Subscription
from app.services.renewal_service import renewal_service
from app.services.payment_service import payment_service
from app.bot.keyboards import get_payment_methods_keyboard


async def show_renewal_subscriptions(query, context):
    """Show list of subscriptions to renew"""
    user = await User.find_one(User.telegram_id == query.from_user.id)
    active_subs = await renewal_service.get_active_subscriptions(user)
    
    text = "🔄 **تمدید اشتراک**\n\nیک اشتراک انتخاب کنید:\n\n"
    
    keyboard = []
    for sub in active_subs:
        eligibility = await renewal_service.check_renewal_eligibility(sub)
        status = "⏰ منقضی شده" if eligibility['is_expired'] else f"✅ {eligibility['days_remaining']}روز باقیمانده"
        keyboard.append([InlineKeyboardButton(f"{sub.base_name} ({status})", callback_data=f"renew_sub_{sub.id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_renewal_plans(query, context, sub_id):
    """Show plans for renewal"""
    print(f"🔍 show_renewal_plans called with sub_id: {sub_id}")
    
    # Clear old renewal context data
    context.user_data.pop("renewal_duration_days", None)
    context.user_data.pop("renewal_price", None)
    context.user_data.pop("is_unlimited_renewal", None)
    context.user_data.pop("renewal_plan_id", None)
    
    subscription = await Subscription.get(sub_id)
    eligibility = await renewal_service.check_renewal_eligibility(subscription)
    
    # Check if subscription is unlimited by finding original plan
    is_unlimited = await renewal_service.is_unlimited_subscription(subscription)
    
    # Escape special characters for Markdown
    escaped_name = subscription.base_name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
    
    text = f"📦 **تمدید {escaped_name}**\n\n"
    if is_unlimited:
        text += f"📊 {eligibility['days_remaining']}روز باقیمانده | ترافیک: نامحدود\n\n"
    else:
        text += f"📊 {eligibility['days_remaining']}روز | {eligibility['traffic_remaining_gb']:.0f}گیگ باقیمانده\n\n"
    
    keyboard = []
    
    if is_unlimited:
        # For unlimited subscriptions, show only time-based options
        text += "افزودن زمان (ترافیک نامحدود):"
        renewal_options = [
            {"duration_days": 30, "price": 420000, "label": "1 ماه"},
            {"duration_days": 60, "price": 750000, "label": "2 ماه"},
            {"duration_days": 90, "price": 1050000, "label": "3 ماه"}
        ]
        for option in renewal_options:
            price_display = int(option["price"] / 1000)
            button_text = f"💰 {price_display}تومان | +{option['duration_days']}روز | نامحدود"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"renew_unlimited_{sub_id}_{option['duration_days']}_{option['price']}")])
    else:
        # For limited subscriptions, show traffic-based plans
        text += "یک پلن انتخاب کنید:"
        plans = await VPNPlan.find(VPNPlan.is_active == True, VPNPlan.traffic_limit_gb != None).to_list()
        for plan in plans:
            price_display = int(plan.price / 1000)
            traffic_display = f"{plan.traffic_limit_gb}گیگ"
            button_text = f"💰 {price_display}تومان | +{plan.duration_days}روز | +{traffic_display}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"renew_plan_{sub_id}_{plan.id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="renew_subscription")])
    
    context.user_data["renewing_subscription_id"] = str(sub_id)
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def process_unlimited_renewal_payment(query, context, sub_id, duration_days, price):
    """Process unlimited renewal payment selection"""
    context.user_data["renewing_subscription_id"] = sub_id
    context.user_data["renewal_duration_days"] = duration_days
    context.user_data["renewal_price"] = price
    context.user_data["is_unlimited_renewal"] = True
    
    print(f"🔍 Setting renewal payment for sub_id: {sub_id}")
    
    text = "💳 **روش پرداخت را انتخاب کنید**\n\n"
    text += "برای تمدید اشتراک، روش پرداخت خود را انتخاب کنید:"
    
    # Custom keyboard with back to renewal plans
    back_callback = f"renew_sub_{sub_id}"
    print(f"🔍 Back button callback: {back_callback}")
    
    keyboard = [
        [InlineKeyboardButton("💳 کارت به کارت", callback_data="payment_card_to_card")],
        [InlineKeyboardButton("₿ ارز دیجیتال", callback_data="payment_crypto")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data=back_callback)]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def process_renewal_payment(query, context, sub_id, plan_id):
    """Process renewal payment selection"""
    context.user_data["renewing_subscription_id"] = sub_id
    context.user_data["renewal_plan_id"] = plan_id
    
    text = "💳 **روش پرداخت را انتخاب کنید**\n\n"
    text += "برای تمدید اشتراک، روش پرداخت خود را انتخاب کنید:"
    
    # Custom keyboard with back to renewal plans
    keyboard = [
        [InlineKeyboardButton("💳 کارت به کارت", callback_data="payment_card_to_card")],
        [InlineKeyboardButton("₿ ارز دیجیتال", callback_data="payment_crypto")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data=f"renew_sub_{sub_id}")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def create_renewal_order(query, context, payment_method):
    """Create order for renewal"""
    sub_id = context.user_data.get("renewing_subscription_id")
    user = await User.find_one(User.telegram_id == query.from_user.id)
    subscription = await Subscription.get(sub_id)
    
    # Check if unlimited renewal
    if context.user_data.get("is_unlimited_renewal"):
        duration_days = int(context.user_data.get("renewal_duration_days"))
        price = int(context.user_data.get("renewal_price"))
        
        # Create a temporary plan object for unlimited renewal
        plan = VPNPlan(
            name=f"{subscription.base_name} - تمدید {duration_days} روز",
            duration_days=duration_days,
            price=price,
            traffic_limit_gb=None,
            is_active=True
        )
        await plan.save()
    else:
        plan_id = context.user_data.get("renewal_plan_id")
        plan = await VPNPlan.get(plan_id)
    
    # Create renewal order
    order = Order(
        user=user,
        vpn_plan=plan,
        protocol="v2ray",
        price=plan.price,
        status=OrderStatus.PAYMENT_PENDING
    )
    await order.save()
    
    # Create payment
    payment = await payment_service.create_payment_request(order, payment_method, user.telegram_id)
    
    # CRITICAL: Mark this payment as renewal in database
    payment.is_renewal = True
    payment.renewal_subscription_id = str(sub_id)
    await payment.save()
    
    print(f"✅ Renewal payment created: {payment.id}")
    print(f"🔍 is_renewal = True")
    print(f"🔍 renewal_subscription_id = {str(sub_id)}")
    
    instructions = payment_service.get_payment_instructions(payment)
    await query.edit_message_text(
        instructions + "\n\n📸 **پس از پرداخت، عکس رسید را ارسال کنید**",
        parse_mode="Markdown"
    )


async def confirm_renewal_payment(query, context, payment_id):
    """Admin confirms renewal payment"""
    from app.models.payment import Payment
    
    await query.answer("⏳ در حال تمدید اشتراک...")
    
    payment = await Payment.get(payment_id)
    await payment_service.confirm_payment(payment, query.from_user.id)
    
    order = await Order.get(payment.order_id)
    plan = await order.vpn_plan.fetch()
    
    # Get subscription to renew from payment record
    subscription = await Subscription.get(payment.renewal_subscription_id)
    
    # Extend subscription
    result = await renewal_service.extend_subscription(subscription, plan, order)
    
    # Clean up renewal flags
    context.bot_data.pop(f"renewal_sub_{payment_id}", None)
    context.bot_data.pop(f"is_renewal_{payment_id}", None)
    
    # Notify user
    user = await User.find_one(User.telegram_id == payment.user_telegram_id)
    
    escaped_name = subscription.base_name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
    text = "✅ **اشتراک تمدید شد!**\n\n"
    text += f"📦 **اشتراک:** {escaped_name}\n"
    text += f"⏱️ **تاریخ انقضا جدید:** {result['new_expiry'].strftime('%Y-%m-%d')}\n"
    
    # Show unlimited if plan has no traffic limit
    if plan.traffic_limit_gb is None:
        text += f"📊 **ترافیک کل:** نامحدود\n\n"
    else:
        text += f"📊 **ترافیک کل:** {result['new_traffic_limit_gb']:.0f}گیگ\n\n"
    
    text += "🔄 کانفیگ های شما به صورت خودکار بروزرسانی شدند."
    
    await context.bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
    
    # Update admin message
    try:
        escaped_admin_name = subscription.base_name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
        await query.edit_message_caption(
            caption=f"✅ **تمدید تأیید شد**\n\n"
                   f"کاربر: {user.first_name}\n"
                   f"اشتراک: {escaped_admin_name}\n"
                   f"مبلغ: {int(payment.amount / 1000)}تومان",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error: {e}")
