from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime
from app.models.user import User
from app.models.vpn_plan import VPNPlan
from app.models.order import Order
from app.models.subscription import Subscription
from app.bot.keyboards import (
    get_main_menu_keyboard, 
    get_channel_verification_keyboard,
    get_protocol_selection_keyboard,
    get_duration_selection_keyboard,
    get_vpn_plans_keyboard, 
    get_delivery_options_keyboard,
    get_subscription_keyboard,
    get_persistent_menu_keyboard,
    get_payment_methods_keyboard
)
from app.services.vpn_service import vpn_service
from app.services.payment_service import payment_service
from app.models.payment import Payment
from app.core.config import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Check channel membership first"""
    user_data = update.effective_user
    
    # Create or get user
    user = await User.find_one(User.telegram_id == user_data.id)
    if not user:
        user = User(
            telegram_id=user_data.id,
            username=user_data.username,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            is_active=True
        )
        await user.save()
    
    # Check channel membership immediately
    await check_channel_membership_on_start(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "buy_vpn":
        await show_protocol_selection(query, context)
    elif data == "renew_subscription":
        from app.bot.handlers.renewal import show_renewal_subscriptions
        await show_renewal_subscriptions(query, context)
    elif data == "new_purchase":
        context.user_data["skip_renewal_check"] = True
        await show_protocol_selection(query, context)
    elif data.startswith("renew_sub_"):
        sub_id = data.replace("renew_sub_", "")
        from app.bot.handlers.renewal import show_renewal_plans
        await show_renewal_plans(query, context, sub_id)
    elif data.startswith("renew_unlimited_"):
        parts = data.replace("renew_unlimited_", "").split("_")
        sub_id, duration_days, price = parts[0], parts[1], parts[2]
        from app.bot.handlers.renewal import process_unlimited_renewal_payment
        await process_unlimited_renewal_payment(query, context, sub_id, duration_days, price)
    elif data.startswith("renew_plan_"):
        parts = data.replace("renew_plan_", "").split("_")
        sub_id, plan_id = parts[0], parts[1]
        from app.bot.handlers.renewal import process_renewal_payment
        await process_renewal_payment(query, context, sub_id, plan_id)
    elif data == "verify_channel":
        await verify_channel_membership(query, context)
    elif data.startswith("protocol_"):
        protocol = data.split("_")[1]
        context.user_data["selected_protocol"] = protocol
        await show_duration_selection(query, protocol)
    elif data.startswith("duration_"):
        duration = data.split("_")[1]
        context.user_data["selected_duration"] = duration
        protocol = context.user_data.get("selected_protocol", "v2ray")
        await show_vpn_plans(query, protocol, int(duration))
    elif data.startswith("plan_"):
        plan_id = data.split("_")[1]
        context.user_data["selected_plan_id"] = plan_id
        context.user_data["waiting_for_config_name"] = True
        await ask_config_name(query)
    elif data.startswith("payment_"):
        payment_method = data.replace("payment_", "", 1)
        # Check if this is a renewal payment
        if context.user_data.get("renewal_plan_id") or context.user_data.get("is_unlimited_renewal"):
            from app.bot.handlers.renewal import create_renewal_order
            await create_renewal_order(query, context, payment_method)
        else:
            await create_payment_request(query, context, payment_method)
    elif data.startswith("confirm_payment_"):
        payment_id = data.split("_")[2]
        # Check if this is a renewal payment from database
        payment = await Payment.get(payment_id)
        print(f"🔍 Checking payment {payment_id}: is_renewal={payment.is_renewal}")
        if payment.is_renewal:
            from app.bot.handlers.renewal import confirm_renewal_payment
            await confirm_renewal_payment(query, context, payment_id)
        else:
            await confirm_payment_admin(query, context, payment_id)
    elif data.startswith("reject_payment_"):
        payment_id = data.split("_")[2]
        await reject_payment_admin(query, context, payment_id)
    elif data == "my_subscription":
        await show_my_subscription(query)
    elif data.startswith("sub_"):
        config_email = data.replace("sub_", "")
        await show_subscription_details(query, config_email)
    elif data == "my_configs":
        await show_my_configs(query)
    elif data.startswith("config_"):
        config_email = data.replace("config_", "")
        await show_config_options(query, config_email)
    elif data.startswith("send_sub_"):
        config_email = data.replace("send_sub_", "")
        await send_subscription_link(query, config_email)
    elif data.startswith("send_ind_"):
        config_email = data.replace("send_ind_", "")
        await send_individual_configs(query, context, config_email)
    elif data == "my_orders":
        await show_my_orders(query)
    elif data == "help":
        await show_help(query)
    elif data == "back_to_main":
        await show_main_menu(query)
    elif data == "back_to_protocols":
        await show_protocol_selection(query, context)
    elif data == "back_to_duration":
        protocol = context.user_data.get("selected_protocol", "v2ray")
        await show_duration_selection(query, protocol)
    elif data == "back_to_plans":
        protocol = context.user_data.get("selected_protocol", "v2ray")
        duration = int(context.user_data.get("selected_duration", 1))
        await show_vpn_plans(query, protocol, duration)
    elif data == "restart":
        await restart_bot(query, context)
    elif data == "test_config":
        await handle_test_config(query, context)
    elif data == "skip_coupon":
        context.user_data["waiting_for_coupon"] = False
        await show_payment_methods_callback(query)
    elif data.startswith("admin_") or data == "broadcast_confirm" or data == "broadcast_cancel":
        from app.bot.handlers.admin import handle_admin_callback
        await handle_admin_callback(query, context)


async def check_channel_membership_on_start(update, context):
    """Check channel membership immediately after /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if not settings.ENABLE_CHANNEL_VERIFICATION:
        print("⚠️ Channel verification disabled")
        await show_welcome_menu(update, user_name)
        return
    
    print(f"🔍 Initial check for user {user_id} in channel {settings.NEWS_CHANNEL_USERNAME}")
    
    try:
        member = await context.bot.get_chat_member(settings.NEWS_CHANNEL_USERNAME, user_id)
        print(f"✅ Initial member status: {member.status}")
        if member.status in ['member', 'administrator', 'creator']:
            await show_welcome_menu(update, user_name)
            return
    except Exception as e:
        print(f"❌ Initial check error: {str(e)}")
        # If bot can't check membership, skip verification
        if "bot is not a member" in str(e).lower() or "chat not found" in str(e).lower():
            print("⚠️ Bot cannot verify membership - skipping verification")
            await show_welcome_menu(update, user_name)
            return
    
    # User is not a member, require channel join
    text = f"خوش آمدید {user_name}! 🎉\n\n"
    text += "🔒 **لطفا جهت استفاده از ربات عضو چنل اطلاع رسانی شوید**\n\n"
    text += "برای استفاده از این ربات VPN، ابتدا باید در کانال خبری ما عضو شوید:\n\n"
    text += f"📢 **{settings.NEWS_CHANNEL_USERNAME}**\n"
    text += "• دریافت اخبار و به‌روزرسانی‌های VPN\n"
    text += "• آشنایی با ویژگی‌های جدید\n"
    text += "• دریافت اطلاعیه‌های مهم\n\n"
    text += "پس از عضویت، روی 'عضو شدم' کلیک کنید."
    
    await update.message.reply_text(
        text, 
        reply_markup=get_channel_verification_keyboard(settings.NEWS_CHANNEL_URL),
        parse_mode="Markdown"
    )

async def show_welcome_menu(update, user_name):
    """Show welcome menu after successful verification"""
    from app.core.panel_config import panel_config
    
    text = f"خوش آمدید {user_name}! 🎉\n\n"
    text += "🚀 **سیستم VPN مولتی لوکیشن**\n"
    text += "✅ سرورهای متعدد در سراسر جهان\n"
    text += "✅ تمام پروتکلها در یک اشتراک\n"
    text += "✅ تعویض خودکار سرور\n\n"
    text += "یک گزینه انتخاب کنید:"
    
    # Create persistent reply keyboard
    test_config = panel_config.get_test_config_settings()
    keyboard = [
        ["🛒 خرید یا تمدید VPN", "📊 اشتراک من"],
        ["📦 کانفیگ های من", "📋 فاکتور های من"],
        ["ℹ️ راهنما", "🔄 شروع مجدد"]
    ]
    if test_config.get('enabled', False):
        keyboard.insert(1, ["🧪 تست رایگان"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def verify_channel_membership(query, context):
    """Verify channel membership after user claims to have joined"""
    user_id = query.from_user.id
    user_name = query.from_user.first_name
    
    print(f"🔍 Checking membership for user {user_id} in channel {settings.NEWS_CHANNEL_USERNAME}")
    
    try:
        member = await context.bot.get_chat_member(settings.NEWS_CHANNEL_USERNAME, user_id)
        print(f"✅ Member status: {member.status}")
        
        if member.status in ['member', 'administrator', 'creator']:
            text = f"✅ **تأیید موفق!**\n\n"
            text += f"خوش آمدید {user_name}! 🎉\n\n"
            text += "🚀 **سیستم VPN مولتی لوکیشن**\n"
            text += "✅ سرورهای متعدد در سراسر جهان\n"
            text += "✅ تمام پروتکلها در یک اشتراک\n"
            text += "✅ تعویض خودکار سرور\n\n"
            text += "یک گزینه انتخاب کنید:"
            
            # Create persistent reply keyboard
            keyboard = [
                ["🛒 خرید یا تمدید VPN", "📊 اشتراک من"],
                ["📦 کانفیگ های من", "📋 فاکتور های من"],
                ["ℹ️ راهنما", "🔄 شروع مجدد"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
            
            # Delete the original message and send a new one with keyboard
            await query.message.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return
        else:
            print(f"❌ User status '{member.status}' not in allowed statuses")
    except Exception as e:
        print(f"❌ Error checking membership: {str(e)}")
        # If bot can't check membership (not admin), skip verification
        if "bot is not a member" in str(e).lower() or "chat not found" in str(e).lower():
            print("⚠️ Bot cannot verify membership - allowing access")
            text = f"⚠️ **تأیید خودکار**\n\n"
            text += f"خوش آمدید {user_name}! 🎉\n\n"
            text += "🚀 **سیستم VPN مولتی لوکیشن**\n"
            text += "✅ سرورهای متعدد در سراسر جهان\n"
            text += "✅ تمام پروتکلها در یک اشتراک\n"
            text += "✅ تعویض خودکار سرور\n\n"
            text += "یک گزینه انتخاب کنید:"
            
            keyboard = [
                ["🛒 خرید یا تمدید VPN", "📊 اشتراک من"],
                ["📦 کانفیگ های من", "📋 فاکتور های من"],
                ["ℹ️ راهنما", "🔄 شروع مجدد"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
            
            await query.message.delete()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return
    
    # Verification failed - try to edit, if fails then delete and send new
    text = "❌ **تأیید ناموفق**\n\n"
    text += f"شما هنوز عضو {settings.NEWS_CHANNEL_USERNAME} نیستید.\n\n"
    text += "**راهحلهای ممکن:**\n"
    text += "1. مطمئن شوید در کانال عضو شده اید\n"
    text += "2. چند دقیقه صبر کنید (تأخیر سیستم)\n"
    text += "3. از کانال خارج شوید و دوباره عضو شوید\n\n"
    text += "سپس روی 'عضو شدم' کلیک کنید."
    
    try:
        await query.edit_message_text(
            text,
            reply_markup=get_channel_verification_keyboard(settings.NEWS_CHANNEL_URL),
            parse_mode="Markdown"
        )
    except Exception:
        # If edit fails, delete and send new message
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=get_channel_verification_keyboard(settings.NEWS_CHANNEL_URL),
            parse_mode="Markdown"
        )

async def show_main_menu(query):
    """Show main menu"""
    text = "🏠 **منوی اصلی**\n\nیک گزینه انتخاب کنید:"
    try:
        await query.edit_message_text(text, reply_markup=get_persistent_menu_keyboard(), parse_mode="Markdown")
    except Exception:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=get_persistent_menu_keyboard(), parse_mode="Markdown")

async def restart_bot(query, context):
    """Restart bot - clear user data and show welcome"""
    # Clear user context data
    context.user_data.clear()
    
    user_name = query.from_user.first_name
    text = f"🔄 **ربات مجدداً شروع شد!**\n\n"
    text += f"خوش آمدید {user_name}! 🎉\n\n"
    text += "🚀 **سیستم VPN مولتی لوکیشن**\n"
    text += "✅ سرورهای متعدد در سراسر جهان\n"
    text += "✅ تمام پروتکلها در یک اشتراک\n"
    text += "✅ تعویض خودکار سرور\n\n"
    text += "یک گزینه انتخاب کنید:"
    
    try:
        await query.edit_message_text(text, reply_markup=get_persistent_menu_keyboard(), parse_mode="Markdown")
    except Exception:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=get_persistent_menu_keyboard(), parse_mode="Markdown")

async def show_protocol_selection_message(update):
    """Show protocol selection for message handler - check for existing subscriptions first"""
    from app.services.renewal_service import renewal_service
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = await User.find_one(User.telegram_id == update.effective_user.id)
    if user:
        active_subs = await renewal_service.get_active_subscriptions(user)
        
        if active_subs:
            # User has active subscriptions - offer renewal or new purchase
            text = "🔄 **شما اشتراک فعال دارید!**\n\n"
            text += "چه کاری میخواهید انجام دهید؟\n\n"
            text += "🔄 **تمدید اشتراک** - افزودن زمان و ترافیک به اشتراک فعلی\n"
            text += "🆕 **خرید جدید** - ایجاد اشتراک جدید با نام متفاوت"
            
            keyboard = [
                [InlineKeyboardButton("🔄 تمدید اشتراک", callback_data="renew_subscription")],
                [InlineKeyboardButton("🆕 خرید جدید", callback_data="new_purchase")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")]
            ]
            
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
    
    # No active subscriptions - show protocol selection
    text = "🔧 **انتخاب پروتکل VPN**\n\n"
    text += "🔹 **V2Ray** - مدرن، سریع، امن\n"
    # text += "   • VLESS Reality (مستقیم و تونل)\n"
    # text += "   • VLESS WebSocket TLS\n"
    # text += "   • VLESS gRPC TLS\n"
    # text += "   • Trojan Reality\n\n"
    # text += "🔸 **OpenVPN** - به زودی\n"
    # text += "🔹 **WireGuard** - به زودی\n\n"
    text += "پروتکل مورد نظر خود را انتخاب کنید:"
    
    await update.message.reply_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")

async def show_my_subscription_message(update):
    """Show config names grouped by subscription"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    user = await User.find_one(User.telegram_id == update.effective_user.id)
    if not user or not user.subscriptions:
        text = "❌ **اشتراک فعالی یافت نشد**\n\nشما هنوز هیچ اشتراک VPN فعال ندارید."
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    # Get base names from subscriptions
    config_names = set()
    for sub_link in user.subscriptions:
        subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if subscription and subscription.is_active:
            config_names.add(subscription.base_name)
    
    if not config_names:
        text = "❌ **اشتراک فعالی یافت نشد**"
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    text = "📊 **اشتراکهای من:**\n\nروی یک اشتراک کلیک کنید:"
    
    keyboard = []
    for name in sorted(config_names):
        keyboard.append([InlineKeyboardButton(name, callback_data=f"sub_{name}")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_my_orders_message(update):
    """Show last 10 orders for message handler"""
    user = await User.find_one(User.telegram_id == update.effective_user.id)
    if not user:
        text = "❌ **کاربر یافت نشد**\n\nلطفاً ابتدا یک پلن VPN خریداری کنید."
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    orders = await Order.find(Order.user.id == user.id).sort(-Order.created_at).limit(10).to_list()
    
    if not orders:
        text = "📋 **بدون فاکتور**\n\nشما هنوز هیچ فاکتوری ندارید.\n\nاز 🛒 خرید VPN برای شروع استفاده کنید!"
    else:
        status_map = {
            "pending": "در انتظار",
            "payment_pending": "در انتظار پرداخت",
            "paid": "پرداخت شده",
            "completed": "تکمیل شده",
            "cancelled": "لغو شده",
            "expired": "منقضی شده"
        }
        
        text = "📋 **فاکتور های من (10 آخرین):**\n\n"
        
        for i, order in enumerate(orders):
            plan = await order.vpn_plan.fetch()
            status_str = str(order.status).lower().replace('orderstatus.', '')
            status_persian = status_map.get(status_str, status_str)
            
            text += f"📦 {plan.name}\n"
            text += f"🆔 Order ID: `{str(order.id)}`\n"
            text += f"💰 {int(order.price / 1000):,} تومان\n"
            text += f"🔧 {order.protocol.upper()}\n"
            text += f"📅 ایجاد: {order.created_at.strftime('%Y-%m-%d')}\n"
            text += f"📊 وضعیت: {status_persian}\n"
            if order.expires_at:
                text += f"⏱️ انقضا: {order.expires_at.strftime('%Y-%m-%d')}\n"
            
            # Add separator line between orders (except after last one)
            if i < len(orders) - 1:
                text += "\n" + "─" * 20 + "\n\n"
            else:
                text += "\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_subscription_details(query, base_name):
    """Show traffic details for a specific subscription"""
    from app.services.traffic_service import traffic_service
    from app.models.order import Order
    
    # Show loading message
    await query.answer("⏳ لطفا صبر کنید...")
    await query.edit_message_text("⏳ **در حال دریافت اطلاعات...**\n\nلطفاً چند لحظه صبر کنید.", parse_mode="Markdown")
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد", parse_mode="Markdown")
        return
    
    # Find subscription by base_name
    subscription = None
    for sub_link in user.subscriptions:
        sub = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if sub and sub.is_active and sub.base_name == base_name:
            subscription = sub
            break
    
    if not subscription:
        await query.edit_message_text("❌ اشتراک یافت نشد", parse_mode="Markdown")
        return
    
    # Sync traffic from all configs
    total_used = 0
    for config_item in subscription.configs:
        try:
            from app.services.xui_service import XUIService
            from app.core.panel_config import panel_config
            
            # Find panel dynamically by name
            panel_key, panel_info = panel_config.get_panel_by_name(config_item.panel_name)
            if not panel_key:
                continue
            
            panel_service = XUIService(panel_key)
            stats = await panel_service.get_client_stats(config_item.inbound_id, config_item.client_email)
            if stats:
                total_used += stats.get("down", 0) + stats.get("up", 0)
        except Exception as e:
            print(f"❌ Error syncing {config_item.client_email}: {e}")
    
    subscription.traffic_used = total_used
    await subscription.save()
    
    total_limit = subscription.total_limit or 0
    expires_at = subscription.expires_at
    config_count = len(subscription.configs)
    
    # Get plan and order ID from subscription's order
    plan_name = "نامشخص"
    plan_is_unlimited = False
    order_id = None
    orders = await Order.find(Order.user.id == user.id).to_list()
    for order in orders:
        try:
            if hasattr(order, 'panel_configs') and order.panel_configs:
                for pc in order.panel_configs:
                    pc_obj = await pc.fetch() if hasattr(pc, 'fetch') else pc
                    if pc_obj and pc_obj.id == subscription.id:
                        plan = await order.vpn_plan.fetch() if hasattr(order.vpn_plan, 'fetch') else order.vpn_plan
                        if plan:
                            plan_name = plan.name
                            plan_is_unlimited = plan.traffic_limit_gb is None
                        order_id = str(order.id)
                        break
        except Exception as e:
            print(f"❌ Error fetching plan: {e}")
            continue
    
    used_gb = total_used / (1024**3)
    limit_gb = total_limit / (1024**3) if total_limit else 0
    remaining_gb = max(0, limit_gb - used_gb) if limit_gb else float('inf')
    usage_percent = round((used_gb / limit_gb) * 100, 1) if limit_gb else 0
    days_remaining = max(0, (expires_at - datetime.utcnow()).days) if expires_at else 0
    
    # Escape underscores for Markdown
    escaped_name = base_name.replace("_", "\\_")
    
    text = f"📊 **اشتراک: {escaped_name}**\n\n"
    if order_id:
        text += f"🆔 **Order ID:** `{order_id}`\n"
    text += f"📦 **پلن:** {plan_name}\n"
    text += f"• مصرف شده: {round(used_gb, 2)}GB\n"
    
    if plan_is_unlimited:
        text += f"• حجم: نامحدود\n"
    elif limit_gb:
        text += f"• کل حجم: {limit_gb}GB\n"
        if remaining_gb != float('inf'):
            text += f"• باقیمانده: {round(remaining_gb, 2)}GB\n"
        text += f"• درصد مصرف: {usage_percent}%\n"
    
    text += f"• روزهای باقیمانده: {days_remaining}\n"
    text += f"• کانفیگ ها: {config_count}\n\n"
    text += "🔄 **به روزرسانی:** اطلاعات به صورت خودکار به روزرسانی میشود"
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="my_subscription")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_my_configs_message(update):
    """Show user's config names with clickable buttons for message handler"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = await User.find_one(User.telegram_id == update.effective_user.id)
    if not user or not user.subscriptions:
        text = "❌ **کانفیگی یافت نشد**\n\nشما هنوز هیچ کانفیگ VPN ندارید."
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    # Get base names from subscriptions
    config_names = set()
    for sub_link in user.subscriptions:
        subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if subscription and subscription.is_active:
            config_names.add(subscription.base_name)
    
    if not config_names:
        text = "❌ **کانفیگ فعالی یافت نشد**"
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    text = "📦 **کانفیگ های من:**\n\nروی یک کانفیگ کلیک کنید:"
    
    keyboard = []
    for name in sorted(config_names):
        keyboard.append([InlineKeyboardButton(name, callback_data=f"config_{name}")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_my_configs(query):
    """Show user's config names with buttons"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user or not user.subscriptions:
        text = "❌ **کانفیگی یافت نشد**\n\nشما هنوز هیچ کانفیگ VPN ندارید."
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        return
    
    # Get base names from subscriptions
    config_names = set()
    for sub_link in user.subscriptions:
        subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if subscription and subscription.is_active:
            config_names.add(subscription.base_name)
    
    if not config_names:
        text = "❌ **کانفیگ فعالی یافت نشد**"
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        return
    
    text = "📦 **کانفیگ های من:**\n\nروی یک کانفیگ کلیک کنید:"
    
    keyboard = []
    for name in sorted(config_names):
        keyboard.append([InlineKeyboardButton(name, callback_data=f"config_{name}")])
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_config_options(query, config_email):
    """Show options for a specific config"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # Escape underscores for Markdown
    escaped_email = config_email.replace("_", "\\_")
    
    text = f"📦 **کانفیگ: {escaped_email}**\n\nچه کاری میخواهید انجام دهید؟"
    
    keyboard = [
        [InlineKeyboardButton("📱 لینک اشتراک", callback_data=f"send_sub_{config_email}")],
        [InlineKeyboardButton("📋 کانفیگ های جداگانه", callback_data=f"send_ind_{config_email}")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="my_configs")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def send_subscription_link(query, base_name):
    """Send subscription link for specific subscription"""
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        await query.answer("❌ کاربر یافت نشد", show_alert=True)
        return
    
    # Find subscription by base_name
    subscription = None
    for sub_link in user.subscriptions:
        sub = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if sub and sub.is_active and sub.base_name == base_name:
            subscription = sub
            break
    
    if not subscription:
        await query.answer("❌ اشتراک یافت نشد", show_alert=True)
        return
    
    sub_url = f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{subscription.subscription_token}"
    
    text = f"📱 **لینک اشتراک شما:**\n\n"
    text += f"`{sub_url}`\n\n"
    text += "📝 کانفیگ های این اشتراک در این لینک قرار دارند."
    
    await query.message.reply_text(text, parse_mode="Markdown")
    await query.answer("✅ لینک ها ارسال شد")

async def show_help_message(update):
    """Show help for message handler"""
    text = "ℹ️ **راهنما و پشتیبانی**\n\n"
    text += "🤖 **ربات VPN مولتی لوکیشن**\n"
    text += "کانفیگ VPN از سرورهای متعدد در سراسر جهان دریافت کنید!\n\n"
    text += f"📢 **کانال ما:**\n"
    text += f"• {settings.NEWS_CHANNEL_USERNAME} - اخبار و به روزرسانی\n\n"
    text += f"📞 **نیاز به کمک دارید؟** با {settings.SUPPORT_USERNAME} تماس بگیرید"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def restart_bot_message(update, context):
    """Restart bot for message handler"""
    from app.core.panel_config import panel_config
    context.user_data.clear()
    
    user_name = update.effective_user.first_name
    text = f"🔄 **ربات مجدداً شروع شد!**\n\n"
    text += f"خوش آمدید {user_name}! 🎉\n\n"
    text += "🚀 **سیستم VPN مولتی لوکیشن**\n"
    text += "✅ سرورهای متعدد در سراسر جهان\n"
    text += "✅ تمام پروتکلها در یک اشتراک\n"
    text += "✅ تعویض خودکار سرور\n\n"
    text += "یک گزینه انتخاب کنید:"
    
    test_config = panel_config.get_test_config_settings()
    keyboard = [
        ["🛒 خرید یا تمدید VPN", "📊 اشتراک من"],
        ["📦 کانفیگ های من", "📋 فاکتور های من"],
        ["ℹ️ راهنما", "🔄 شروع مجدد"]
    ]
    if test_config.get('enabled', False):
        keyboard.insert(1, ["🧪 تست رایگان"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_protocol_selection(query, context=None):
    """Show protocol selection - check for existing subscriptions first"""
    from app.services.renewal_service import renewal_service
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # Skip renewal check if user explicitly chose new purchase
    skip_check = context and context.user_data.get("skip_renewal_check", False)
    
    if skip_check and context:
        context.user_data.pop("skip_renewal_check", None)
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if user and not skip_check:
        active_subs = await renewal_service.get_active_subscriptions(user)
        
        if active_subs:
            # User has active subscriptions - offer renewal or new purchase
            text = "🔄 **شما اشتراک فعال دارید!**\n\n"
            text += "چه کاری میخواهید انجام دهید؟\n\n"
            text += "🔄 **تمدید اشتراک** - افزودن زمان و ترافیک به اشتراک فعلی\n"
            text += "🆕 **خرید جدید** - ایجاد اشتراک جدید با نام متفاوت"
            
            keyboard = [
                [InlineKeyboardButton("🔄 تمدید اشتراک", callback_data="renew_subscription")],
                [InlineKeyboardButton("🆕 خرید جدید", callback_data="new_purchase")],
                [InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")]
            ]
            
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            except Exception:
                await query.message.delete()
                await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
    
    # No active subscriptions - show protocol selection
    text = "🔧 **انتخاب پروتکل VPN**\n\n"
    text += "🔹 **V2Ray** - مدرن، سریع، امن\n"
    # text += "   • VLESS Reality (مستقیم و تونل)\n"
    # text += "   • VLESS WebSocket TLS\n"
    # text += "   • VLESS gRPC TLS\n"
    # text += "   • Trojan Reality\n\n"
    # text += "🔸 **OpenVPN** - به زودی\n"
    # text += "🔹 **WireGuard** - به زودی\n\n"
    text += "پروتکل مورد نظر خود را انتخاب کنید:"
    
    try:
        await query.edit_message_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")
    except Exception:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")

async def show_duration_selection(query, protocol):
    """Show duration selection"""
    if protocol != "v2ray":
        text = f"🚧 **{protocol.upper()} به زودی**\n\n"
        text += "این پروتکل هنوز در دسترس نیست.\n"
        text += "لطفاً فعلاً V2Ray را انتخاب کنید."
        await query.edit_message_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")
        return
    
    text = "📅 **مدت اشتراک را انتخاب کنید**\n\n"
    text += "🌍 **سیستم مولتی لوکیشن:**\n"
    text += "• سرورهای آلمان 🇩🇪، ترکیه 🇹🇷\n"
    text += "• تمام پروتکلها در یک اشتراک\n"
    text += "• لود بلنسینگ هوشمند\n\n"
    text += "مدت مورد نظر خود را انتخاب کنید:"
    
    await query.edit_message_text(text, reply_markup=get_duration_selection_keyboard(), parse_mode="Markdown")

async def show_vpn_plans(query, protocol, duration_months):
    """Show available VPN plans for selected duration"""
    print(f"🔍 show_vpn_plans called: protocol={protocol}, duration_months={duration_months}")
    
    # Filter plans by duration
    duration_days = duration_months * 30
    all_plans = await VPNPlan.find(
        VPNPlan.is_active == True,
        VPNPlan.duration_days == duration_days
    ).to_list()
    
    # Filter out temporary renewal plans (contain 'تمدید' in name)
    plans = [plan for plan in all_plans if 'تمدید' not in plan.name]
    
    print(f"🔍 Found {len(plans)} plans for {duration_days} days (filtered from {len(all_plans)} total)")
    for plan in plans:
        print(f"  - {plan.name}: {plan.traffic_limit_gb}GB, {plan.price} Rials")
    
    if not plans:
        await query.edit_message_text(
            f"هیچ پلن {duration_months} ماهه در دسترس نیست.\n{settings.SUPPORT_USERNAME}",
            parse_mode="Markdown"
        )
        return
    
    text = f"📦 **پلن های {duration_months} ماهه**\n\n"
    text += "💰 **قیمت ها:**\n"
    for plan in plans:
        traffic = f"{plan.traffic_limit_gb}GB" if plan.traffic_limit_gb else "نامحدود"
        price = int(plan.price / 1000)
        text += f"• {traffic}: {price:,} تومان\n"
    
    text += "\n🌍 **ویژگی ها:**\n"
    text += "• چندین سرور خارجی\n"
    text += "• لود بلنسینگ خودکار\n"
    text += "• تمام پروتکلها\n\n"
    text += "پلن مورد نظر خود را انتخاب کنید:"
    
    await query.edit_message_text(text, reply_markup=get_vpn_plans_keyboard(plans, duration_months), parse_mode="Markdown")

async def show_delivery_options(query):
    """Show delivery options"""
    text = "📦 **روش تحویل را انتخاب کنید**\n\n"
    text += "📱 **لینک اشتراک** (توصیه شده)\n"
    text += "• یک لینک با تمام کانفیگ ها\n"
    text += "• ب هروزرسانی خودکار\n"
    text += "• آسان برای استفاده\n\n"
    text += "📋 **کانفیگ های جداگانه**\n"
    text += "• کانفیگ جداگانه برای هر سرور\n"
    text += "• نیاز به تنظیم دستی\n"
    text += "• مناسب برای کاربران پیشرفته\n\n"
    text += "روش مورد نظر خود را انتخاب کنید:"
    
    await query.edit_message_text(text, reply_markup=get_delivery_options_keyboard(), parse_mode="Markdown")

async def ask_config_name(query):
    """Ask user for custom config name"""
    from telegram.ext import ContextTypes
    
    text = "یک نام دلخواه برای کانفیگتون انتخاب کنید\n\n"
    text += "مثال: mamad, akbar , asghar\n\n"
    text += "💡 **نکته:** نام باید فقط انگلیسی و حداکثر 20 کاراکتر باشد."
    
    await query.edit_message_text(text, parse_mode="Markdown")

async def ask_coupon_code(update):
    """Ask user for coupon code"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    text = "🎁 **کد تخفیف دارید؟**\n\n"
    text += "اگر کد تخفیف دارید، آن را تایپ کنید.\n"
    text += "اگر ندارید، روی دکمه زیر کلیک کنید."
    
    keyboard = [[InlineKeyboardButton("⏭️ بدون کد ادامه بده", callback_data="skip_coupon")]]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_config_name_input(update, context):
    """Handle user's config name input"""
    config_name = update.message.text.strip()
    
    # Validate English only
    if not config_name.isascii():
        await update.message.reply_text(
            "❌ **فقط حروف انگلیسی مجاز است!**\n\n"
            "لطفاً نام را به انگلیسی وارد کنید.\n"
            "مثال: Home, Work, Mobile",
            parse_mode="Markdown"
        )
        return
    
    # Validate name
    if len(config_name) > 20:
        await update.message.reply_text(
            "❌ **نام خیلی بلند است!**\n\n"
            "لطفاً نامی کمتر از 20 کاراکتر وارد کنید.",
            parse_mode="Markdown"
        )
        return
    
    if len(config_name) < 2:
        await update.message.reply_text(
            "❌ **نام خیلی کوتاه است!**\n\n"
            "لطفاً نامی حداقل 2 کاراکتر وارد کنید.",
            parse_mode="Markdown"
        )
        return
    
    # Save config name
    context.user_data["config_name"] = config_name
    context.user_data["waiting_for_config_name"] = False
    
    # Ask for coupon code
    context.user_data["waiting_for_coupon"] = True
    await ask_coupon_code(update)

async def show_payment_methods(update):
    """Show payment method selection"""
    text = "💳 **روش پرداخت را انتخاب کنید**\n\n"
    text += "💳 **کارت به کارت**\n"
    text += "• پرداخت با کارت بانکی\n"
    text += "• تأیید سریع (حداکثر 2 ساعت)\n"
    text += "• پشتیبانی از تمام بانکها\n\n"
    text += "₿ **ارز دیجیتال**\n"
    text += "• Bitcoin, USDT, Ethereum\n"
    text += "• ناشناس و امن\n"
    text += "• تأیید خودکار\n\n"
    text += "روش پرداخت مورد نظر خود را انتخاب کنید:"
    
    await update.message.reply_text(text, reply_markup=get_payment_methods_keyboard(), parse_mode="Markdown")

async def show_payment_methods_callback(query, context=None):
    """Show payment method selection for callback query"""
    text = "💳 **روش پرداخت را انتخاب کنید**\n\n"
    text += "💳 **کارت به کارت**\n"
    text += "• پرداخت با کارت بانکی\n"
    text += "• تأیید سریع (حداکثر 2 ساعت)\n"
    text += "• پشتیبانی از تمام بانکها\n\n"
    text += "₿ **ارز دیجیتال**\n"
    text += "• Bitcoin, USDT, Ethereum\n"
    text += "• ناشناس و امن\n"
    text += "• تأیید خودکار\n\n"
    text += "روش پرداخت مورد نظر خود را انتخاب کنید:"
    
    # Use custom keyboard with proper back button
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [InlineKeyboardButton("💳 کارت به کارت", callback_data="payment_card_to_card")],
        [InlineKeyboardButton("₿ ارز دیجیتال", callback_data="payment_crypto")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_plans")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def create_payment_request(query, context, payment_method):
    """Create payment request"""
    print(f"🔍 Payment method received: {payment_method}")
    
    plan_id = context.user_data.get("selected_plan_id")
    protocol = context.user_data.get("selected_protocol", "v2ray")
    delivery_type = context.user_data.get("delivery_type", "subscription")
    coupon_code = context.user_data.get("coupon_code")
    
    if not plan_id:
        keyboard = [[InlineKeyboardButton("🔄 شروع مجدد", callback_data="restart")]]
        await query.edit_message_text(
            "خطا: هیچ پلنی انتخاب نشده. لطفاً دوباره شروع کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Get user and plan
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        await query.edit_message_text("خطا: کاربر یافت نشد. لطفاً /start را بزنید.")
        return
    
    plan = await VPNPlan.get(plan_id)
    
    # Apply coupon if provided
    final_price = plan.price
    discount_amount = 0
    if coupon_code:
        from app.models.coupon import Coupon
        coupon = await Coupon.find_one(Coupon.code == coupon_code)
        if coupon and coupon.is_valid():
            discount_amount = coupon.calculate_discount(plan.price)
            final_price = plan.price - discount_amount
    
    from app.models.order import OrderStatus
    order = Order(
        user=user,
        vpn_plan=plan,
        protocol=protocol,
        price=final_price,
        original_price=plan.price if coupon_code else None,
        coupon_code=coupon_code,
        discount_amount=discount_amount if coupon_code else None,
        status=OrderStatus.PAYMENT_PENDING
    )
    await order.save()
    
    # Cancel any old pending payments for this user
    old_payments = await Payment.find(
        Payment.user_telegram_id == user.telegram_id,
        Payment.status == "pending"
    ).to_list()
    for old_payment in old_payments:
        old_payment.status = "expired"
        await old_payment.save()
        print(f"❌ Cancelled old pending payment: {old_payment.id}")
    
    # Create payment request - pass user telegram_id directly
    payment = await payment_service.create_payment_request(order, payment_method, user.telegram_id)
    
    # Store config name in bot_data for admin confirmation
    config_name = context.user_data.get("config_name")
    if config_name:
        context.bot_data[f"config_name_{user.telegram_id}"] = config_name
    
    # Store delivery type for later
    context.user_data["payment_id"] = str(payment.id)
    context.user_data["order_id"] = str(order.id)
    
    # Show payment instructions
    instructions = payment_service.get_payment_instructions(payment)
    
    await query.edit_message_text(
        instructions + "\n\n📸 **پس از پرداخت، عکس رسید را ارسال کنید**",
        parse_mode="Markdown"
    )

async def confirm_payment_admin(query, context, payment_id):
    """Admin confirms payment"""
    await query.answer("⏳ در حال ایجاد کانفیگ ها...")
    
    payment = await Payment.get(payment_id)
    await payment_service.confirm_payment(payment, query.from_user.id)
    
    # Get order and create VPN configs
    order = await Order.get(payment.order_id)
    
    # Track coupon usage
    if order.coupon_code:
        from app.models.coupon import Coupon, CouponUsage
        coupon = await Coupon.find_one(Coupon.code == order.coupon_code)
        if coupon:
            coupon.current_uses += 1
            # Convert to int to avoid floating point precision issues
            coupon.total_discount_given += int(order.discount_amount or 0)
            coupon.total_revenue += int(order.price)
            await coupon.save()
            
            usage = CouponUsage(
                coupon_code=order.coupon_code,
                user=order.user,
                vpn_plan=order.vpn_plan,
                order_id=str(order.id),
                discount_amount=int(order.discount_amount or 0),
                original_price=int(order.original_price or order.price),
                final_price=int(order.price)
            )
            await usage.insert()
    
    # Get config name from order's user context (stored during payment creation)
    config_name = context.bot_data.get(f"config_name_{payment.user_telegram_id}")
    
    # Create VPN subscription
    result = await vpn_service.create_subscription(order, config_name)
    
    # Clear the stored config name after successful creation
    context.bot_data.pop(f"config_name_{payment.user_telegram_id}", None)
    
    # Send subscription link to user (always)
    user = await User.find_one(User.telegram_id == payment.user_telegram_id)
    
    if result and result.get("total_configs", 0) > 0:
        await send_subscription_to_user(context, user, result, order.vpn_plan, str(order.id))
    
    # Update admin message (edit caption since it's a photo message)
    try:
        await query.edit_message_caption(
            caption=f"✅ **پرداخت تأیید شد**\n\n"
                   f"کاربر: {user.first_name}\n"
                   f"مبلغ: {int(payment.amount / 1000):,} تومان\n"
                   f"کانفیگ ها ارسال شد: {result.get('total_configs', 0)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error updating admin message: {e}")

async def reject_payment_admin(query, context, payment_id):
    """Admin rejects payment"""
    payment = await Payment.get(payment_id)
    
    # Get order and cancel it
    from app.models.order import Order, OrderStatus
    order = await Order.get(payment.order_id)
    order.status = OrderStatus.CANCELLED
    await order.save()
    
    await payment_service.reject_payment(payment, query.from_user.id)
    
    # Clear the stored config name
    context.bot_data.pop(f"config_name_{payment.user_telegram_id}", None)
    
    # Notify user
    user = await User.find_one(User.telegram_id == payment.user_telegram_id)
    await context.bot.send_message(
        chat_id=payment.user_telegram_id,
        text=f"❌ **پرداخت رد شد**\n\n"
            "رسید ارسالی شما تأیید نشد.\n\n"
            "لطفاً دوباره از 🛍️ خرید VPN استفاده کنید.\n\n"
            f"برای راهنمایی با {settings.SUPPORT_USERNAME} تماس بگیرید.",
        parse_mode="Markdown"
    )

    
    # Update admin message (edit caption since it's a photo message)
    try:
        await query.edit_message_caption(
            caption=f"❌ **پرداخت رد شد**\n\n"
                   f"کاربر: {user.first_name}\n"
                   f"مبلغ:{payment.amount / 1000} تومان\n"
                   f"کاربر مطلع شد.",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error updating admin message: {e}")

async def send_subscription_to_user(context, user, result, plan, order_id=None):
    """Send subscription URL to user"""
    if hasattr(plan, 'fetch'):
        plan = await plan.fetch()
    
    # Display traffic
    if result.get('display_traffic'):
        traffic_text = f"{result['display_traffic']}GB"
    else:
        traffic_text = "نامحدود"
    
    text = "✅ **پرداخت تأیید شد! اشتراک VPN آماده است**\n\n"
    text += f"📦 **پلن:** {plan.name}\n"
    text += f"💰 **قیمت:** {int(plan.price / 1000):,} تومان\n"
    text += f"📊 **حجم:** {traffic_text}\n"
    text += f"🌍 **تعداد کانفیگ:** {result['total_configs']}\n"
    text += f"⏱️ **مدت:** {plan.duration_days} روز\n\n"
    
    if order_id:
        text += f"🆔 **Order ID:** `{order_id}`\n"
        text += "💡 این شناسه را برای پشتیبانی نگه دارید\n\n"
    
    text += "📱 **لینک اشتراک شما:**\n\n"
    text += f"`{result['subscription_url']}`\n\n"
    text += "📝 کانفیگ های این اشتراک در این لینک قرار دارند.\n\n"
    
    await context.bot.send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="Markdown"
    )
    
    # Send individual configs
    if result.get('individual_configs'):
        configs_text = "📋 **کانفیگ های جداگانه:**\n\n"
        for i, cfg in enumerate(result['individual_configs'], 1):
            flag = cfg.get('panel_flag', '🌍')
            config_url = cfg.get('config', cfg) if isinstance(cfg, dict) else cfg
            escaped_config = str(config_url).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            configs_text += f"{flag} <b>کانفیگ {i}:</b>\n<code>{escaped_config}</code>\n\n"
        
        configs_text += "💡 برای دریافت مجدد لینک ها، از دکمه 'کانفیگ های من' استفاده کنید."
        
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=configs_text,
            parse_mode="HTML"
        )



async def send_individual_configs(query, context, base_name):
    """Send individual configs for a specific base name (all inbounds)"""
    # Show loading message
    await query.answer("⏳ لطفا صبر کنید...")
    await query.edit_message_text("⏳ **در حال دریافت کانفیگ ها...**\n\nلطفاً چند لحظه صبر کنید.", parse_mode="Markdown")
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        await query.edit_message_text("❌ کاربر یافت نشد", parse_mode="Markdown")
        return
    
    # Find subscription with matching base_name
    configs = []
    print(f"🔍 Looking for subscription with base name: {base_name}")
    
    for sub_link in user.subscriptions:
        subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if subscription and subscription.is_active and subscription.base_name == base_name:
            configs = await vpn_service.get_user_configs(subscription.subscription_token)
            configs = [{"config": cfg, "flag": "🌍"} for cfg in configs]
            break
    
    print(f"📊 Total configs found: {len(configs)}")
    
    if not configs:
        await query.edit_message_text("❌ کانفیگی یافت نشد", parse_mode="Markdown")
        return
    
    escaped_name = base_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    text = f"📋 <b>کانفیگ های {escaped_name}:</b>\n\n"
    for i, cfg in enumerate(configs, 1):
        flag = cfg.get('flag', '🌍')
        config_url = cfg.get('config', cfg) if isinstance(cfg, dict) else cfg
        escaped_config = str(config_url).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text += f"{flag} <b>کانفیگ {i}:</b>\n<code>{escaped_config}</code>\n\n"
    
    await query.message.reply_text(text, parse_mode="HTML")
    await query.answer("✅ کانفیگ ها ارسال شد")

async def show_my_subscription(query):
    """Show config names grouped by subscription"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user or not user.subscriptions:
        text = "❌ **اشتراک فعالی یافت نشد**\n\nشما هنوز هیچ اشتراک VPN فعال ندارید."
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        return
    
    # Get base names from subscriptions
    config_names = []
    for sub_link in user.subscriptions:
        subscription = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if subscription and subscription.is_active:
            config_names.append(subscription.base_name)
    
    if not config_names:
        text = "❌ **اشتراک فعالی یافت نشد**"
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        return
    
    text = "📊 **اشتراکهای من:**\n\nروی یک اشتراک کلیک کنید:"
    
    keyboard = []
    for name in sorted(set(config_names)):
        keyboard.append([InlineKeyboardButton(name, callback_data=f"sub_{name}")])
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_my_orders(query):
    """Show last 10 orders"""
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        text = "❌ **کاربر یافت نشد**\n\nلطفاً ابتدا یک پلن VPN خریداری کنید."
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        return
    
    orders = await Order.find(Order.user.id == user.id).sort(-Order.created_at).limit(10).to_list()
    
    if not orders:
        text = "📋 **بدون فاکتور**\n\nشما هنوز هیچ فاکتوری ندارید.\n\nاز 🛒 خرید VPN برای شروع استفاده کنید!"
    else:
        text = "📋 **فاکتور های من (10 آخرین):**\n\n"
        
        status_map = {
            "pending": "در انتظار",
            "payment_pending": "در انتظار پرداخت",
            "paid": "پرداخت شده",
            "completed": "تکمیل شده",
            "cancelled": "لغو شده",
            "expired": "منقضی شده"
        }
        
        for i, order in enumerate(orders):
            plan = await order.vpn_plan.fetch()
            status_str = str(order.status).lower().replace('orderstatus.', '')
            status_persian = status_map.get(status_str, status_str)
            
            text += f"📦 {plan.name}\n"
            text += f"🆔 Order ID: `{str(order.id)}`\n"
            text += f"💰 {int(order.price / 1000):,} تومان\n"
            text += f"🔧 {order.protocol.upper()}\n"
            text += f"📅 ایجاد: {order.created_at.strftime('%Y-%m-%d')}\n"
            text += f"📊 وضعیت: {status_persian}\n"
            if order.expires_at:
                text += f"⏱️ انقضا: {order.expires_at.strftime('%Y-%m-%d')}\n"
            
            # Add separator line between orders (except after last one)
            if i < len(orders) - 1:
                text += "\n" + "─" * 20 + "\n\n"
            else:
                text += "\n"
    
    await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def show_help(query):
    """Show help information"""
    text = "ℹ️ **راهنما و پشتیبانی**\n\n"
    text += "🤖 **ربات VPN مولتی لوکیشن**\n"
    text += "کانفیگ VPN از سرورهای متعدد در سراسر جهان دریافت کنید!\n\n"
    text += f"📢 **کانال ما:**\n"
    text += f"• {settings.NEWS_CHANNEL_USERNAME} - اخبار و به روزرسانی\n\n"
    text += "🔧 **ویژگی ها:**\n"
    text += "• پروتکل های متعدد (V2Ray, OpenVPN(به زودی), WireGuard(به زودی))\n"
    text += "• سرورهای متعدد (آلمان، ترکیه، بیشتر در راه)\n"
    text += "• تعویض خودکار\n"
    text += "• لینکهای اشتراک\n"
    text += "• کانفیگ های جداگانه\n\n"
    text += "📋 **نحوه استفاده:**\n"
    text += "1. لطفا در کانال خبری ما عضو شوید\n"
    text += "2. پروتکل را انتخاب کنید (V2Ray توصیه شده)\n"
    text += "3. یک پلن انتخاب کنید\n"
    text += "4. روش تحویل را انتخاب کنید\n"
    text += "5. کانفیگ های خود را دریافت کنید!\n\n"
    text += f"📞 **نیاز به کمک دارید؟** با {settings.SUPPORT_USERNAME} تماس بگیرید"
    
    await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")




async def handle_test_config(query, context):
    """Handle test config request"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[TEST_CONFIG] Handler called by user {query.from_user.id}")
    
    from app.core.panel_config import panel_config
    
    test_config = panel_config.get_test_config_settings()
    logger.info(f"[TEST_CONFIG] Test config settings: {test_config}")
    
    if not test_config.get('enabled', False):
        logger.warning(f"[TEST_CONFIG] Test config disabled for user {query.from_user.id}")
        await query.answer("❌ تست رایگان غیرفعال است", show_alert=True)
        return
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        logger.error(f"[TEST_CONFIG] User not found: {query.from_user.id}")
        await query.answer("❌ کاربر یافت نشد", show_alert=True)
        return
    
    logger.info(f"[TEST_CONFIG] User found: {user.id}, checking existing subscriptions")
    
    for sub_link in user.subscriptions:
        sub = await sub_link.fetch() if hasattr(sub_link, 'fetch') else sub_link
        if sub and sub.is_active and "test" in sub.base_name.lower():
            logger.warning(f"[TEST_CONFIG] User {user.id} already has test subscription: {sub.base_name}")
            await query.answer("❌ شما قبلاً تست رایگان دریافت کردهاید", show_alert=True)
            return
    
    logger.info(f"[TEST_CONFIG] Creating test config for user {user.id}")
    await query.answer("⏳ در حال ایجاد تست رایگان...")
    await query.edit_message_text("⏳ **در حال ایجاد کانفیگ تست...**\n\nلطفاً چند لحظه صبر کنید.", parse_mode="Markdown")
    
    from app.models.vpn_plan import VPNPlan
    from app.models.order import Order, OrderStatus
    
    duration_days = test_config.get('duration_days', 10)
    traffic_gb = test_config.get('traffic_gb', 2)
    
    logger.info(f"[TEST_CONFIG] Creating test plan: {traffic_gb}GB, {duration_days} days")
    
    test_plan = VPNPlan(
        name=f"تست {traffic_gb}GB - {duration_days} روز",
        traffic_limit_gb=traffic_gb,
        duration_days=duration_days,
        price=0,
        is_active=True
    )
    await test_plan.insert()
    logger.info(f"[TEST_CONFIG] Test plan created: {test_plan.id}")
    
    order = Order(
        user=user,
        vpn_plan=test_plan,
        protocol="v2ray",
        price=0,
        status=OrderStatus.COMPLETED
    )
    await order.save()
    logger.info(f"[TEST_CONFIG] Order created: {order.id}")
    
    try:
        result = await vpn_service.create_subscription(order, f"test_{user.telegram_id}")
        logger.info(f"[TEST_CONFIG] Subscription result: {result}")
    except Exception as e:
        logger.error(f"[TEST_CONFIG] Error creating subscription: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ **خطا در ایجاد تست**\n\nلطفاً بعداً دوباره تلاش کنید.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    if result and result.get("total_configs", 0) > 0:
        logger.info(f"[TEST_CONFIG] Success! Total configs: {result.get('total_configs')}")
        text = "✅ **تست رایگان آماده است!**\n\n"
        text += f"📦 **پلن:** {test_plan.name}\n"
        text += f"📊 **حجم:** {traffic_gb}GB\n"
        text += f"🌍 **تعداد کانفیگ:** {result['total_configs']}\n"
        text += f"⏱️ **مدت:** {duration_days} روز\n\n"
        text += "📱 **لینک اشتراک:**\n"
        text += f"`{result['subscription_url']}`\n\n"
        text += "💡 برای خرید پلن کامل از 🛒 خرید VPN استفاده کنید"
        
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        
        if result.get('individual_configs'):
            configs_text = "📋 **کانفیگ های جداگانه:**\n\n"
            for i, cfg in enumerate(result['individual_configs'], 1):
                flag = cfg.get('panel_flag', '🌍')
                config_url = cfg.get('config', cfg) if isinstance(cfg, dict) else cfg
                escaped_config = str(config_url).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                configs_text += f"{flag} <b>کانفیگ {i}:</b>\n<code>{escaped_config}</code>\n\n"
            
            await query.message.reply_text(configs_text, parse_mode="HTML")
    else:
        logger.error(f"[TEST_CONFIG] Failed to create configs. Result: {result}")
        await query.edit_message_text(
            "❌ **خطا در ایجاد تست**\n\nلطفاً بعداً دوباره تلاش کنید.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )


async def show_test_config_inline(update):
    """Show test config button as inline keyboard for message handler"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from app.core.panel_config import panel_config
    
    test_config = panel_config.get_test_config_settings()
    if not test_config.get('enabled', False):
        await update.message.reply_text("❌ تست رایگان غیرفعال است", parse_mode="Markdown")
        return
    
    text = "🧪 **تست رایگان VPN**\n\n"
    text += f"📊 **حجم:** {test_config.get('traffic_gb', 2)}GB\n"
    text += f"⏱️ **مدت:** {test_config.get('duration_days', 10)} روز\n\n"
    text += "💡 هر کاربر فقط یک بار میتواند تست رایگان دریافت کند.\n\n"
    text += "برای دریافت تست رایگان روی دکمه زیر کلیک کنید:"
    
    keyboard = [[InlineKeyboardButton("🧪 دریافت تست رایگان", callback_data="test_config")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
