from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu_keyboard():
    """Main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🛒 خرید VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("📊 اشتراک من", callback_data="my_subscription")],
        [InlineKeyboardButton("📦 کانفیگ های من", callback_data="my_configs")],
        [InlineKeyboardButton("📋 فاکتور های من", callback_data="my_orders")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_channel_verification_keyboard(channel_url):
    """Channel verification keyboard"""
    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=channel_url)],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="verify_channel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_protocol_selection_keyboard():
    """Protocol selection keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔹 V2Ray (VLESS + Trojan)", callback_data="protocol_v2ray")],
        # [InlineKeyboardButton("🔸 OpenVPN (به زودی)", callback_data="protocol_openvpn")],
        # [InlineKeyboardButton("🔹 WireGuard (به زودی)", callback_data="protocol_wireguard")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_duration_selection_keyboard():
    """Duration selection keyboard"""
    keyboard = [
        [InlineKeyboardButton("📅 1 ماهه", callback_data="duration_1")],
        [InlineKeyboardButton("📅 2 ماهه", callback_data="duration_2")],
        [InlineKeyboardButton("📅 3 ماهه", callback_data="duration_3")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back_to_protocols")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_vpn_plans_keyboard(plans, duration_months):
    """VPN plans selection keyboard with prices"""
    keyboard = []
    for plan in plans:
        traffic = f"{plan.traffic_limit_gb}GB" if plan.traffic_limit_gb else "نامحدود"
        price = int(plan.price / 1000)
        text = f"{traffic} - {price:,} تومان"
        callback_data = f"plan_{plan.id}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 برگشت", callback_data="back_to_duration")])
    return InlineKeyboardMarkup(keyboard)

def get_delivery_options_keyboard():
    """Delivery options keyboard"""
    keyboard = [
        [InlineKeyboardButton("📱 لینک اشتراک (توصیه شده)", callback_data="delivery_subscription")],
        [InlineKeyboardButton("📋 کانفیگ های جداگانه", callback_data="delivery_individual")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back_to_plans")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscription_keyboard(subscription_url):
    """Subscription result keyboard"""
    keyboard = [
        [InlineKeyboardButton("📱 باز کردن اشتراک", url=subscription_url)],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_individual_configs_keyboard():
    """Individual configs result keyboard"""
    keyboard = [
        [InlineKeyboardButton("📋 کپی تمام کانفیگها", callback_data="copy_all_configs")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_persistent_menu_keyboard():
    """Persistent menu keyboard with restart button"""
    keyboard = [
        [InlineKeyboardButton("🛒 خرید VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton("📊 اشتراک من", callback_data="my_subscription")],
        [InlineKeyboardButton("📦 کانفیگ های من", callback_data="my_configs")],
        [InlineKeyboardButton("📋 فاکتور های من", callback_data="my_orders")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help"), InlineKeyboardButton("🔄 شروع مجدد", callback_data="restart")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods_keyboard():
    """Payment methods selection keyboard"""
    keyboard = [
        [InlineKeyboardButton("💳 کارت به کارت", callback_data="payment_card_to_card")],
        [InlineKeyboardButton("₿ ارز دیجیتال", callback_data="payment_crypto")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_plans")]
    ]
    return InlineKeyboardMarkup(keyboard)
