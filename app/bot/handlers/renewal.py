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
    
    text = "🔄 **تمدید اشتراک**\n\nکدام اشتراک را میخواهید تمدید کنید؟\n\n"
    
    keyboard = []
    for sub in active_subs:
        eligibility = await renewal_service.check_renewal_eligibility(sub)
        status = "⏰ منقضی شده" if eligibility['is_expired'] else f"✅ {eligibility['days_remaining']} روز باقیمانده"
        keyboard.append([InlineKeyboardButton(f"{sub.base_name} ({status})", callback_data=f"renew_sub_{sub.id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_renewal_plans(query, context, sub_id):
    """Show plans for renewal"""
    subscription = await Subscription.get(sub_id)
    eligibility = await renewal_service.check_renewal_eligibility(subscription)
    
    plans = await VPNPlan.find(VPNPlan.is_active == True).to_list()
    
    # Escape special characters for Markdown
    escaped_name = subscription.base_name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")
    
    text = f"📦 **تمدید {escaped_name}**\n\n"
    text += f"📊 وضعیت فعلی:\n"
    text += f"• روزهای باقیمانده: {eligibility['days_remaining']}\n"
    text += f"• ترافیک باقیمانده: {eligibility['traffic_remaining_gb']:.2f}GB\n\n"
    text += "یک پلن برای تمدید انتخاب کنید:\n\n"
    
    for plan in plans:
        text += f"📦 **{plan.name}**\n"
        text += f"💰 ${plan.price}\n"
        text += f"⏱️ +{plan.duration_days} روز\n"
        text += f"📊 +{plan.traffic_limit_gb}GB ترافیک\n\n"
    
    keyboard = []
    for plan in plans:
        keyboard.append([InlineKeyboardButton(f"💰 {plan.name} - ${plan.price}", callback_data=f"renew_plan_{sub_id}_{plan.id}")])
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="renew_subscription")])
    
    context.user_data["renewing_subscription_id"] = str(sub_id)
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def process_renewal_payment(query, context, sub_id, plan_id):
    """Process renewal payment selection"""
    context.user_data["renewing_subscription_id"] = sub_id
    context.user_data["renewal_plan_id"] = plan_id
    
    text = "💳 **روش پرداخت را انتخاب کنید**\n\n"
    text += "برای تمدید اشتراک، روش پرداخت خود را انتخاب کنید:"
    
    await query.edit_message_text(text, reply_markup=get_payment_methods_keyboard(), parse_mode="Markdown")


async def create_renewal_order(query, context, payment_method):
    """Create order for renewal"""
    sub_id = context.user_data.get("renewing_subscription_id")
    plan_id = context.user_data.get("renewal_plan_id")
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    subscription = await Subscription.get(sub_id)
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
    
    # Store renewal info
    context.bot_data[f"renewal_sub_{payment.id}"] = str(sub_id)
    
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
    
    # Get subscription to renew
    sub_id = context.bot_data.get(f"renewal_sub_{payment_id}")
    subscription = await Subscription.get(sub_id)
    
    # Extend subscription
    result = await renewal_service.extend_subscription(subscription, plan, order)
    
    # Notify user
    user = await User.find_one(User.telegram_id == payment.user_telegram_id)
    
    text = "✅ **اشتراک تمدید شد!**\n\n"
    text += f"📦 **اشتراک:** {subscription.base_name}\n"
    text += f"💰 **پلن:** {plan.name}\n"
    text += f"⏱️ **تاریخ انقضا جدید:** {result['new_expiry'].strftime('%Y-%m-%d')}\n"
    text += f"📊 **ترافیک کل:** {result['new_traffic_limit_gb']:.0f}GB\n\n"
    text += "🔄 کانفیگ های شما به صورت خودکار بروزرسانی شدند."
    
    await context.bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
    
    # Update admin message
    try:
        await query.edit_message_caption(
            caption=f"✅ **تمدید تأیید شد**\n\n"
                   f"کاربر: {user.first_name}\n"
                   f"اشتراک: {subscription.base_name}\n"
                   f"مبلغ: ${payment.amount}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error: {e}")
