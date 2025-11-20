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
        await show_protocol_selection(query)
    elif data == "renew_subscription":
        from app.bot.handlers.renewal import show_renewal_subscriptions
        await show_renewal_subscriptions(query, context)
    elif data == "new_purchase":
        await show_protocol_selection(query)
    elif data.startswith("renew_sub_"):
        sub_id = data.replace("renew_sub_", "")
        from app.bot.handlers.renewal import show_renewal_plans
        await show_renewal_plans(query, context, sub_id)
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
        await show_vpn_plans(query, protocol)
    elif data.startswith("plan_"):
        plan_id = data.split("_")[1]
        context.user_data["selected_plan_id"] = plan_id
        context.user_data["waiting_for_config_name"] = True
        await ask_config_name(query)
    elif data.startswith("payment_"):
        payment_method = data.replace("payment_", "", 1)
        # Check if this is a renewal payment
        if context.user_data.get("renewing_subscription_id"):
            from app.bot.handlers.renewal import create_renewal_order
            await create_renewal_order(query, context, payment_method)
        else:
            await create_payment_request(query, context, payment_method)
    elif data.startswith("confirm_payment_"):
        payment_id = data.split("_")[2]
        # Check if this is a renewal payment
        if context.bot_data.get(f"renewal_sub_{payment_id}"):
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
        await show_protocol_selection(query)
    elif data == "back_to_plans":
        protocol = context.user_data.get("selected_protocol", "v2ray")
        await show_vpn_plans(query, protocol)
    elif data == "restart":
        await restart_bot(query, context)
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
    text += "🔒 **عضویت در کانال الزامی است**\n\n"
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
    text = f"خوش آمدید {user_name}! 🎉\n\n"
    text += "🚀 **سیستم VPN چند پنله**\n"
    text += "✅ سرورهای متعدد در سراسر جهان\n"
    text += "✅ تمام پروتکلها در یک اشتراک\n"
    text += "✅ تعویض خودکار سرور\n\n"
    text += "یک گزینه انتخاب کنید:"
    
    # Create persistent reply keyboard
    keyboard = [
        ["🛒 خرید VPN", "📊 اشتراک من"],
        ["📦 کانفیگ های من", "📋 فاکتور های من"],
        ["ℹ️ راهنما", "🔄 شروع مجدد"]
    ]
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
            text += "🚀 **سیستم VPN چند پنله**\n"
            text += "✅ سرورهای متعدد در سراسر جهان\n"
            text += "✅ تمام پروتکلها در یک اشتراک\n"
            text += "✅ تعویض خودکار سرور\n\n"
            text += "یک گزینه انتخاب کنید:"
            
            # Create persistent reply keyboard
            keyboard = [
                ["🛒 خرید VPN", "📊 اشتراک من"],
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
            text += "🚀 **سیستم VPN چند پنله**\n"
            text += "✅ سرورهای متعدد در سراسر جهان\n"
            text += "✅ تمام پروتکلها در یک اشتراک\n"
            text += "✅ تعویض خودکار سرور\n\n"
            text += "یک گزینه انتخاب کنید:"
            
            keyboard = [
                ["🛒 خرید VPN", "📊 اشتراک من"],
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
    text += "1. مطمئن شوید در کانال عضو شدهاید\n"
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
    text += "🚀 **سیستم VPN چند پنله**\n"
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
    text += "   • VLESS Reality (مستقیم و تونل)\n"
    text += "   • VLESS WebSocket TLS\n"
    text += "   • VLESS gRPC TLS\n"
    text += "   • Trojan Reality\n\n"
    text += "🔸 **OpenVPN** - به زودی\n"
    text += "🔹 **WireGuard** - به زودی\n\n"
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
    """Show last 5 orders for message handler"""
    user = await User.find_one(User.telegram_id == update.effective_user.id)
    if not user:
        text = "❌ **کاربر یافت نشد**\n\nلطفاً ابتدا یک پلن VPN خریداری کنید."
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    orders = await Order.find(Order.user.id == user.id).sort(-Order.created_at).limit(5).to_list()
    
    if not orders:
        text = "📋 **بدون فاکتور**\n\nشما هنوز هیچ فاکتوری ندارید.\n\nاز 🛒 خرید VPN برای شروع استفاده کنید!"
    else:
        text = "📋 **فاکتور های من (5 آخرین):**\n\n"
        
        for order in orders:
            plan = await order.vpn_plan.fetch()
            status = str(order.status).replace('_', ' ').title()
            text += f"📦 {plan.name}\n"
            text += f"💰 ${order.price}\n"
            text += f"🔧 {order.protocol.upper()}\n"
            text += f"📅 ایجاد: {order.created_at.strftime('%Y-%m-%d')}\n"
            text += f"📊 وضعیت: {status}\n"
            if order.expires_at:
                text += f"⏱️ انقضا: {order.expires_at.strftime('%Y-%m-%d')}\n"
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
            panel_service = XUIService(config_item.panel_name.lower())
            stats = await panel_service.get_client_stats(config_item.inbound_id, config_item.client_email)
            if stats:
                total_used += stats.get("down", 0) + stats.get("up", 0)
        except Exception as e:
            print(f"❌ Error: {e}")
    
    subscription.traffic_used = total_used
    await subscription.save()
    
    total_limit = subscription.total_limit or 0
    expires_at = subscription.expires_at
    config_count = len(subscription.configs)
    
    # Get plan name from order
    plan_name = ""
    orders = await Order.find(Order.user.id == user.id).to_list()
    for order in orders:
        plan = await order.vpn_plan.fetch()
        plan_name = plan.name
        break
    
    used_gb = total_used / (1024**3)
    limit_gb = total_limit / (1024**3) if total_limit else 0
    remaining_gb = max(0, limit_gb - used_gb) if limit_gb else float('inf')
    usage_percent = round((used_gb / limit_gb) * 100, 1) if limit_gb else 0
    days_remaining = max(0, (expires_at - datetime.utcnow()).days) if expires_at else 0
    
    # Escape underscores for Markdown
    escaped_name = base_name.replace("_", "\\_")
    
    text = f"📊 **اشتراک: {escaped_name}**\n\n"
    text += f"📦 **پلن:** {plan_name}\n"
    text += f"• مصرف شده: {round(used_gb, 2)}GB\n"
    if limit_gb:
        text += f"• کل حجم: {limit_gb}GB\n"
        if remaining_gb != float('inf'):
            text += f"• باقیمانده: {round(remaining_gb, 2)}GB\n"
        text += f"• درصد مصرف: {usage_percent}%\n"
    text += f"• روزهای باقیمانده: {days_remaining}\n"
    text += f"• کانفیگها: {config_count}\n\n"
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

async def send_subscription_link(query, config_email):
    """Send subscription link for config"""
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user or not user.subscription_token:
        await query.answer("❌ لینک اشتراک یافت نشد", show_alert=True)
        return
    
    sub_url = f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{user.subscription_token}"
    
    text = f"📱 **لینک اشتراک شما:**\n\n`{sub_url}`\n\nتمام کانفیگ های شما در این لینک قرار دارند."
    
    await query.message.reply_text(text, parse_mode="Markdown")
    await query.answer("✅ لینک ارسال شد")

async def show_help_message(update):
    """Show help for message handler"""
    text = "ℹ️ **راهنما و پشتیبانی**\n\n"
    text += "🤖 **ربات VPN چند پنله**\n"
    text += "کانفیگ VPN از سرورهای متعدد در سراسر جهان دریافت کنید!\n\n"
    text += f"📢 **کانال ما:**\n"
    text += f"• {settings.NEWS_CHANNEL_USERNAME} - اخبار و به روزرسانی\n\n"
    text += f"📞 **نیاز به کمک دارید؟** با {settings.SUPPORT_USERNAME} تماس بگیرید"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def restart_bot_message(update, context):
    """Restart bot for message handler"""
    context.user_data.clear()
    
    user_name = update.effective_user.first_name
    text = f"🔄 **ربات مجدداً شروع شد!**\n\n"
    text += f"خوش آمدید {user_name}! 🎉\n\n"
    text += "🚀 **سیستم VPN چند پنله**\n"
    text += "✅ سرورهای متعدد در سراسر جهان\n"
    text += "✅ تمام پروتکلها در یک اشتراک\n"
    text += "✅ تعویض خودکار سرور\n\n"
    text += "یک گزینه انتخاب کنید:"
    
    keyboard = [
        ["🛒 خرید VPN", "📊 اشتراک من"],
        ["📦 کانفیگ های من", "📋 فاکتور های من"],
        ["ℹ️ راهنما", "🔄 شروع مجدد"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_protocol_selection(query):
    """Show protocol selection - check for existing subscriptions first"""
    from app.services.renewal_service import renewal_service
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user = await User.find_one(User.telegram_id == query.from_user.id)
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
            
            try:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            except Exception:
                await query.message.delete()
                await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return
    
    # No active subscriptions - show protocol selection
    text = "🔧 **انتخاب پروتکل VPN**\n\n"
    text += "🔹 **V2Ray** - مدرن، سریع، امن\n"
    text += "   • VLESS Reality (مستقیم و تونل)\n"
    text += "   • VLESS WebSocket TLS\n"
    text += "   • VLESS gRPC TLS\n"
    text += "   • Trojan Reality\n\n"
    text += "🔸 **OpenVPN** - به زودی\n"
    text += "🔹 **WireGuard** - به زودی\n\n"
    text += "پروتکل مورد نظر خود را انتخاب کنید:"
    
    try:
        await query.edit_message_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")
    except Exception:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")

async def show_vpn_plans(query, protocol):
    """Show available VPN plans"""
    if protocol != "v2ray":
        text = f"🚧 **{protocol.upper()} به زودی**\n\n"
        text += "این پروتکل هنوز در دسترس نیست.\n"
        text += "لطفاً فعلاً V2Ray را انتخاب کنید."
        await query.edit_message_text(text, reply_markup=get_protocol_selection_keyboard(), parse_mode="Markdown")
        return
    
    plans = await VPNPlan.find(VPNPlan.is_active == True).to_list()
    
    if not plans:
        await query.edit_message_text("هیچ پلن VPN در دسترس نیست. لطفاً با پشتیبانی تماس بگیرید.")
        return
    
    text = f"📦 **پلنهای V2Ray**\n\n"
    text += "🌍 **سیستم چند پنله:**\n"
    text += "• سرورهای آلمان 🇩🇪 + ترکیه 🇹🇷\n"
    text += "• تمام پروتکلها شامل\n"
    text += "• ترافیک مشترک در تمام کانفیگها\n\n"
    
    for plan in plans:
        text += f"📦 **{plan.name}**\n"
        text += f"💰 ${plan.price}\n"
        text += f"⏱️ {plan.duration_days} روز\n"
        if plan.traffic_limit_gb:
            text += f"📊 {plan.traffic_limit_gb}GB ترافیک\n"
        else:
            text += f"📊 ترافیک نامحدود\n"
        text += f"📱 {plan.max_connections} اتصال\n"
        text += f"ℹ️ {plan.description}\n\n"
    
    await query.edit_message_text(text, reply_markup=get_vpn_plans_keyboard(plans), parse_mode="Markdown")

async def show_delivery_options(query):
    """Show delivery options"""
    text = "📦 **روش تحویل را انتخاب کنید**\n\n"
    text += "📱 **لینک اشتراک** (توصیه شده)\n"
    text += "• یک لینک با تمام کانفیگها\n"
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
    text += "مثال: Home, Work, Mobile, Laptop\n\n"
    text += "💡 **نکته:** نام باید فقط انگلیسی و حداکثر 20 کاراکتر باشد."
    
    await query.edit_message_text(text, parse_mode="Markdown")

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
    
    # Show payment methods
    await show_payment_methods(update)

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

async def create_payment_request(query, context, payment_method):
    """Create payment request"""
    print(f"🔍 Payment method received: {payment_method}")
    
    plan_id = context.user_data.get("selected_plan_id")
    protocol = context.user_data.get("selected_protocol", "v2ray")
    delivery_type = context.user_data.get("delivery_type", "subscription")
    
    if not plan_id:
        await query.edit_message_text("خطا: هیچ پلنی انتخاب نشده. لطفاً دوباره شروع کنید.")
        return
    
    # Get user and plan
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        await query.edit_message_text("خطا: کاربر یافت نشد. لطفاً /start را بزنید.")
        return
    
    plan = await VPNPlan.get(plan_id)
    
    from app.models.order import OrderStatus
    order = Order(
        user=user,
        vpn_plan=plan,
        protocol=protocol,
        price=plan.price,
        status=OrderStatus.PAYMENT_PENDING
    )
    await order.save()
    
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
    await query.answer("⏳ در حال ایجاد کانفیگها...")
    
    payment = await Payment.get(payment_id)
    await payment_service.confirm_payment(payment, query.from_user.id)
    
    # Get order and create VPN configs
    order = await Order.get(payment.order_id)
    
    # Get config name from order's user context (stored during payment creation)
    config_name = context.bot_data.get(f"config_name_{payment.user_telegram_id}")
    
    # Create VPN subscription
    result = await vpn_service.create_multi_panel_config(order, config_name)
    
    # Send subscription link to user (always)
    user = await User.find_one(User.telegram_id == payment.user_telegram_id)
    
    if result and result.get("total_configs", 0) > 0:
        await send_subscription_to_user(context, user, result, order.vpn_plan)
    
    # Update admin message (edit caption since it's a photo message)
    try:
        await query.edit_message_caption(
            caption=f"✅ **پرداخت تأیید شد**\n\n"
                   f"کاربر: {user.first_name}\n"
                   f"مبلغ: ${payment.amount}\n"
                   f"کانفیگ ها ارسال شد: {result.get('total_configs', 0)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error updating admin message: {e}")

async def reject_payment_admin(query, context, payment_id):
    """Admin rejects payment"""
    payment = await Payment.get(payment_id)
    await payment_service.reject_payment(payment, query.from_user.id)
    
    # Notify user
    user = await User.find_one(User.telegram_id == payment.user_telegram_id)
    await context.bot.send_message(
        chat_id=payment.user_telegram_id,
        text="❌ **پرداخت رد شد**\n\n"
             "رسید ارسالی شما تأیید نشد.\n"
             "لطفاً با پشتیبانی تماس بگیرید.",
        parse_mode="Markdown"
    )
    
    # Update admin message (edit caption since it's a photo message)
    try:
        await query.edit_message_caption(
            caption=f"❌ **پرداخت رد شد**\n\n"
                   f"کاربر: {user.first_name}\n"
                   f"مبلغ: ${payment.amount}\n"
                   f"کاربر مطلع شد.",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Error updating admin message: {e}")

async def send_subscription_to_user(context, user, result, plan):
    """Send subscription URL to user"""
    # Fetch plan if it's a Link object
    if hasattr(plan, 'fetch'):
        plan = await plan.fetch()
    
    text = "✅ **پرداخت تأیید شد! اشتراک VPN آماده است**\n\n"
    text += f"📦 **پلن:** {plan.name}\n"
    text += f"💰 **قیمت:** ${plan.price}\n"
    text += f"🌍 **تعداد کانفیگ:** {result['total_configs']}\n"
    text += f"⏱️ **مدت:** {plan.duration_days} روز\n\n"
    text += "📱 **لینک اشتراک:**\n"
    text += f"`{result['subscription_url']}`\n\n"
    text += "**نحوه استفاده:**\n"
    text += "1. لینک اشتراک را کپی کنید\n"
    text += "2. به کلاینت V2Ray خود اضافه کنید\n"
    text += "3. اشتراک را به روزرسانی کنید\n"
    text += "4. به هر سروری وصل شوید!\n\n"
    text += " نکته: اگر لینک کار نمیکرد کانفیگ هارو به صورت تکی از دکمه کانفیگ های من دریافت کنید\n\n"
    text += "🔄 **تعویض خودکار:** کلاینت خودکار سرور را تغییر میدهد"
    
    await context.bot.send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="Markdown"
    )

async def send_individual_configs_to_user(context, user, result, plan):
    """Send individual configs to user"""
    # Fetch plan if it's a Link object
    if hasattr(plan, 'fetch'):
        plan = await plan.fetch()
    
    configs = result['individual_configs']
    
    text = "✅ **پرداخت تأیید شد! کانفیگ های VPN آماده است**\n\n"
    text += f"📦 **پلن:** {plan.name}\n"
    text += f"🌍 **تعداد کانفیگ:** {len(configs)}\n\n"
    
    # Add all configs
    for i, config_data in enumerate(configs, 1):
        if isinstance(config_data, dict):
            config = config_data['config']
            flag = config_data['panel_flag']
        else:
            config = config_data
            flag = "🌍"
        text += f"{flag} **کانفیگ {i}:**\n`{config}`\n\n"
    
    text += "**نحوه استفاده:**\n"
    text += "1. هر کانفیگ را کپی کنید\n"
    text += "2. به کلاینت V2Ray وارد کنید\n"
    text += "3. وصل شوید و لذت ببرید!"
    
    await context.bot.send_message(
        chat_id=user.telegram_id,
        text=text,
        parse_mode="Markdown"
    )

async def create_vpn_subscription(query, context, delivery_type):
    """Create VPN subscription"""
    plan_id = context.user_data.get("selected_plan_id")
    protocol = context.user_data.get("selected_protocol", "v2ray")
    
    if not plan_id:
        await query.edit_message_text("خطا: هیچ پلنی انتخاب نشده. لطفاً دوباره شروع کنید.")
        return
    
    # Create order
    user = await User.find_one(User.telegram_id == query.from_user.id)
    plan = await VPNPlan.get(plan_id)
    
    order = Order(
        user=user,
        vpn_plan=plan,
        protocol=protocol,
        price=plan.price,
        status="paid"  # Skip payment for now
    )
    await order.save()
    
    # Create multi-panel configs
    await query.edit_message_text("🔄 **در حال ایجاد اشتراک VPN شما...**\n\nلطفاً چند لحظه صبر کنید...", parse_mode="Markdown")
    
    try:
        result = await vpn_service.create_multi_panel_config(order)
        print(f"VPN Service Result: {result}")  # Debug log
        
        # Update subscription URL with domain from settings
        if result and "subscription_url" in result:
            token = result["subscription_url"].split("/")[-1]
            result["subscription_url"] = f"{settings.DEFAULT_SUBSCRIPTION_DOMAIN}/api/v1/subscription/{token}"
        
        if result and result.get("total_configs", 0) > 0:
            if delivery_type == "subscription":
                await send_subscription_result(query, result, plan)
            else:
                await send_individual_configs(query, context, result, plan)
        else:
            error_msg = f"❌ ایجاد کانفیگهای VPN ناموفق.\n\nاطلاعات دیباگ: {result}\n\nلطفاً با پشتیبانی تماس بگیرید."
            await query.edit_message_text(error_msg)
    
    except Exception as e:
        print(f"VPN Creation Error: {str(e)}")  # Debug log
        await query.edit_message_text(f"❌ خطا در ایجاد VPN: {str(e)}")

async def send_subscription_result(query, result, plan):
    """Send subscription URL result"""
    text = "✅ **اشتراک VPN ایجاد شد!**\n\n"
    text += f"📦 **پلن:** {plan.name}\n"
    text += f"💰 **قیمت:** ${plan.price}\n"
    text += f"🌍 **تعداد کانفیگ:** {result['total_configs']}\n"
    text += f"⏱️ **مدت:** {plan.duration_days} روز\n\n"
    text += "📱 **لینک اشتراک:**\n"
    text += f"`{result['subscription_url']}`\n\n"
    text += "**نحوه استفاده:**\n"
    text += "1. لینک اشتراک را کپی کنید\n"
    text += "2. به کلاینت V2Ray خود اضافه کنید\n"
    text += "3. اشتراک را به روزرسانی کنید تا تمام کانفیگ ها را دریافت کنید\n"
    text += "4. به هر سروری وصل شوید!\n\n"
    text += "🔄 **تعویض خودکار:** کلاینت به طور خودکار سرور را تغییر میدهد"
    
    await query.edit_message_text(
        text, 
        reply_markup=get_subscription_keyboard(result['subscription_url']),
        parse_mode="Markdown"
    )

async def send_individual_configs(query, context, base_name):
    """Send individual configs for a specific base name (all inbounds)"""
    # Show loading message
    await query.answer("⏳ لطفا صبر کنید...")
    await query.edit_message_text("⏳ **در حال دریافت کانفیگها...**\n\nلطفاً چند لحظه صبر کنید.", parse_mode="Markdown")
    
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
            from app.services.vpn_service import vpn_service
            await vpn_service.sync_subscription_to_new_panels(subscription)
            print(f"✅ Found subscription: {subscription.base_name} with {len(subscription.configs)} configs")
            
            from app.services.xui_service import XUIService
            
            for config_item in subscription.configs:
                # Get panel info
                panel_info = None
                for pname, pinfo in vpn_service.ENABLED_PANELS.items():
                    if pinfo['name'] == config_item.panel_name:
                        panel_info = pinfo
                        break
                
                if panel_info:
                    try:
                        panel_service = XUIService(pname)
                        inbounds_response = await panel_service.get_inbounds()
                        if inbounds_response and inbounds_response.get("success"):
                            for inbound_data in inbounds_response.get("obj", []):
                                if inbound_data["id"] == config_item.inbound_id:
                                    config_url = vpn_service.generate_config_url_from_item(config_item, inbound_data, panel_info['ip'])
                                    if config_url:
                                        configs.append({"config": config_url, "flag": panel_info['flag']})
                                    break
                    except Exception as e:
                        print(f"❌ Error generating config: {e}")
            break
    
    print(f"📊 Total configs found: {len(configs)}")
    
    if not configs:
        await query.edit_message_text("❌ کانفیگی یافت نشد", parse_mode="Markdown")
        return
    
    escaped_name = base_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    text = f"📋 <b>کانفیگ های {escaped_name}:</b>\n\n"
    for i, cfg in enumerate(configs, 1):
        escaped_config = cfg['config'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text += f"{cfg['flag']} <b>کانفیگ {i}:</b>\n<code>{escaped_config}</code>\n\n"
    
    await query.message.reply_text(text, parse_mode="HTML")
    await query.answer("✅ کانفیگها ارسال شد")

async def send_individual_configs_old(query, context, result, plan):
    """Send individual configs result"""
    configs = result['individual_configs']
    
    text = "✅ **کانفیگ های VPN ایجاد شد!**\n\n"
    text += f"📰 **پلن:** {plan.name}\n"
    text += f"🌍 **تعداد کانفیگ:** {len(configs)}\n\n"
    
    # Add all configs in one message with panel flags
    for i, config_data in enumerate(configs, 1):
        if isinstance(config_data, dict):
            config = config_data['config']
            flag = config_data['panel_flag']
        else:
            # Fallback for old format
            config = config_data
            flag = "🌍"
        text += f"{flag} **کانفیگ {i}:**\n`{config}`\n\n"
    
    # Add instructions
    text += "**نحوه استفاده:**\n"
    text += "1. هر کدام از کانفیگ های بالا را کپی کنید\n"
    text += "2. به کلاینت V2Ray خود وارد کنید\n"
    text += "3. وصل شوید و لذت ببرید!\n\n"
    text += "💡 **نکته:** از کانفیگ های مختلف برای پشتیبانی استفاده کنید"
    
    await query.edit_message_text(text, parse_mode="Markdown")

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
    """Show last 5 orders"""
    user = await User.find_one(User.telegram_id == query.from_user.id)
    if not user:
        text = "❌ **کاربر یافت نشد**\n\nلطفاً ابتدا یک پلن VPN خریداری کنید."
        await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        return
    
    orders = await Order.find(Order.user.id == user.id).sort(-Order.created_at).limit(5).to_list()
    
    if not orders:
        text = "📋 **بدون فاکتور**\n\nشما هنوز هیچ فاکتوری ندارید.\n\nاز 🛒 خرید VPN برای شروع استفاده کنید!"
    else:
        text = "📋 **فاکتور های من (5 آخرین):**\n\n"
        
        for order in orders:
            plan = await order.vpn_plan.fetch()
            text += f"📦 {plan.name}\n"
            text += f"💰 ${order.price}\n"
            text += f"🔧 {order.protocol.upper()}\n"
            text += f"📅 ایجاد: {order.created_at.strftime('%Y-%m-%d')}\n"
            text += f"📊 وضعیت: {order.status.title()}\n"
            if order.expires_at:
                text += f"⏱️ انقضا: {order.expires_at.strftime('%Y-%m-%d')}\n"
            text += "\n"
    
    await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def show_help(query):
    """Show help information"""
    text = "ℹ️ **راهنما و پشتیبانی**\n\n"
    text += "🤖 **ربات VPN چند پنله**\n"
    text += "کانفیگ VPN از سرورهای متعدد در سراسر جهان دریافت کنید!\n\n"
    text += f"📢 **کانال ما:**\n"
    text += f"• {settings.NEWS_CHANNEL_USERNAME} - اخبار و به روزرسانی\n\n"
    text += "🔧 **ویژگی ها:**\n"
    text += "• پروتکل های متعدد (V2Ray, OpenVPN, WireGuard)\n"
    text += "• سرورهای متعدد (آلمان، ترکیه، بیشتر در راه)\n"
    text += "• تعویض خودکار\n"
    text += "• لینکهای اشتراک\n"
    text += "• کانفیگ های جداگانه\n\n"
    text += "📋 **نحوه استفاده:**\n"
    text += "1. در کانال خبری ما عضو شوید (الزامی)\n"
    text += "2. پروتکل را انتخاب کنید (V2Ray توصیه شده)\n"
    text += "3. یک پلن انتخاب کنید\n"
    text += "4. روش تحویل را انتخاب کنید\n"
    text += "5. کانفیگ های خود را دریافت کنید!\n\n"
    text += f"📞 **نیاز به کمک دارید؟** با {settings.SUPPORT_USERNAME} تماس بگیرید"
    
    await query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
