"""Admin-only commands"""
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from app.models.user import User
from app.core.config import settings


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    admin_ids = [int(id.strip()) for id in settings.BOT_ADMIN_IDS.split(",")]
    return user_id in admin_ids


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel with buttons"""
    if not is_admin(update.effective_user.id):
        return
    
    text = "🔑 **پنل مدیریت**\n\n"
    text += "از گزینههای زیر استفاده کنید:"
    
    keyboard = [
        [InlineKeyboardButton("📊 آمار ربات", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("💳 پرداختهای معلق", callback_data="admin_pending")],
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle_admin_callback(query, context):
    """Handle admin panel callbacks"""
    if not is_admin(query.from_user.id):
        await query.answer("❌ شما دسترسی ندارید", show_alert=True)
        return
    
    data = query.data
    
    if data == "admin_stats":
        from app.models.order import Order, OrderStatus
        from app.models.subscription import Subscription
        from app.models.payment import Payment
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        total_users = await User.find_all().count()
        total_orders = await Order.find_all().count()
        total_subs = await Subscription.find({"is_active": True}).count()
        pending_payments = await Payment.find({"status": "pending"}).count()
        
        today_orders = await Order.find(
            Order.created_at >= today_start,
            Order.status == OrderStatus.PAID
        ).to_list()
        
        week_orders = await Order.find(
            Order.created_at >= week_start,
            Order.status == OrderStatus.PAID
        ).to_list()
        
        month_orders = await Order.find(
            Order.created_at >= month_start,
            Order.status == OrderStatus.PAID
        ).to_list()
        
        today_revenue = sum(o.price for o in today_orders)
        week_revenue = sum(o.price for o in week_orders)
        month_revenue = sum(o.price for o in month_orders)
        
        text = "📊 **آمار ربات**\n\n"
        text += f"👥 کاربران: {total_users}\n"
        text += f"📦 سفارشات: {total_orders}\n"
        text += f"✅ اشتراکهای فعال: {total_subs}\n"
        text += f"⏳ پرداختهای معلق: {pending_payments}\n\n"
        
        text += "💰 **فروش:**\n"
        text += f"📅 امروز: {len(today_orders)} فروش | {int(today_revenue / 1000):,} تومان\n"
        text += f"📆 7 روز: {len(week_orders)} فروش | {int(week_revenue / 1000):,} تومان\n"
        text += f"📆 30 روز: {len(month_orders)} فروش | {int(month_revenue / 1000):,} تومان\n"
        
        keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "admin_broadcast_start":
        # Set waiting state
        context.user_data["waiting_for_broadcast"] = True
        
        text = "📢 **ارسال پیام همگانی**\n\n"
        text += "پیام خود را بفرستید:\n"
        text += "• متن\n"
        text += "• عکس (با یا بدون متن)\n"
        text += "• ویدیو (با یا بدون متن)\n\n"
        text += "پس از ارسال، گزینه تأیید نمایش داده میشود."
        
        await query.edit_message_text(text, parse_mode="Markdown")
    
    elif data == "admin_users":
        users = await User.find_all().limit(10).to_list()
        
        text = "👥 **لیست کاربران (10 نفر اول)**\n\n"
        for user in users:
            text += f"• {user.first_name} (@{user.username or 'N/A'}) - ID: `{user.telegram_id}`\n"
        
        keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "admin_pending":
        from app.models.payment import Payment
        
        pending = await Payment.find({"status": "pending"}).limit(5).to_list()
        
        text = "💳 **پرداختهای معلق (5 تا اول)**\n\n"
        if not pending:
            text += "✅ هیچ پرداخت معلقی وجود ندارد."
        else:
            for p in pending:
                text += f"• تومان{p.amount / 1000} - User: `{p.user_telegram_id}`\n"
        
        keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "admin_back":
        text = "🔑 **پنل مدیریت**\n\n"
        text += "از گزینههای زیر استفاده کنید:"
        
        keyboard = [
            [InlineKeyboardButton("📊 آمار ربات", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast_start")],
            [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
            [InlineKeyboardButton("💳 پرداختهای معلق", callback_data="admin_pending")],
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    
    elif data == "broadcast_confirm":
        broadcast_data = context.user_data.get("broadcast_data")
        if not broadcast_data:
            await query.answer("❌ پیامی وجود ندارد", show_alert=True)
            return
        
        admin_ids = [int(id.strip()) for id in settings.BOT_ADMIN_IDS.split(",")]
        users = await User.find_all().to_list()
        await query.edit_message_text(f"⏳ در حال ارسال به {len(users)} کاربر...")
        
        success = 0
        for user in users:
            # Skip admin users
            if user.telegram_id in admin_ids:
                continue
            
            try:
                if broadcast_data["type"] == "forward":
                    await context.bot.forward_message(
                        chat_id=user.telegram_id,
                        from_chat_id=broadcast_data["chat_id"],
                        message_id=broadcast_data["message_id"]
                    )
                elif broadcast_data["type"] == "text":
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=f"📢 **اطلاعیه**\n\n{broadcast_data['text']}",
                        parse_mode="Markdown"
                    )
                elif broadcast_data["type"] == "photo":
                    caption = f"📢 **اطلاعیه**\n\n{broadcast_data['caption']}" if broadcast_data['caption'] else "📢 **اطلاعیه**"
                    await context.bot.send_photo(
                        chat_id=user.telegram_id,
                        photo=broadcast_data["file_id"],
                        caption=caption,
                        parse_mode="Markdown"
                    )
                elif broadcast_data["type"] == "video":
                    caption = f"📢 **اطلاعیه**\n\n{broadcast_data['caption']}" if broadcast_data['caption'] else "📢 **اطلاعیه**"
                    await context.bot.send_video(
                        chat_id=user.telegram_id,
                        video=broadcast_data["file_id"],
                        caption=caption,
                        parse_mode="Markdown"
                    )
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        
        await query.edit_message_text(
            f"✅ **ارسال کامل شد!**\n\n"
            f"• کل: {len(users)}\n"
            f"• موفق: {success}"
        )
        
        context.user_data.pop("broadcast_data", None)
        context.user_data.pop("waiting_for_broadcast", None)
    
    elif data == "broadcast_cancel":
        context.user_data.pop("broadcast_data", None)
        context.user_data.pop("waiting_for_broadcast", None)
        await query.edit_message_text("❌ ارسال پیام لغو شد.")


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message input (text, photo, video)"""
    if not is_admin(update.effective_user.id):
        return
    
    if not context.user_data.get("waiting_for_broadcast"):
        return
    
    users = await User.find_all().to_list()
    
    # Store message data
    broadcast_data = {}
    
    # Check if message is forwarded
    if update.message.forward_from or update.message.forward_from_chat or update.message.forward_date:
        broadcast_data["type"] = "forward"
        broadcast_data["message_id"] = update.message.message_id
        broadcast_data["chat_id"] = update.message.chat_id
    elif update.message.text:
        broadcast_data["type"] = "text"
        broadcast_data["text"] = update.message.text
    elif update.message.photo:
        broadcast_data["type"] = "photo"
        broadcast_data["file_id"] = update.message.photo[-1].file_id
        broadcast_data["caption"] = update.message.caption or ""
    elif update.message.video:
        broadcast_data["type"] = "video"
        broadcast_data["file_id"] = update.message.video.file_id
        broadcast_data["caption"] = update.message.caption or ""
    else:
        await update.message.reply_text("❌ فقط متن، عکس، ویدیو یا پیام فوروارد شده پشتیبانی میشود.")
        return
    
    context.user_data["broadcast_data"] = broadcast_data
    context.user_data["waiting_for_broadcast"] = False
    
    # Show confirmation
    text = f"📢 **تأیید ارسال**\n\n"
    text += f"پیام به {len(users)} کاربر ارسال میشود\n\n"
    
    if broadcast_data["type"] == "forward":
        text += f"پیام فوروارد شده\n\n"
    elif broadcast_data["type"] == "text":
        text += f"متن: _{broadcast_data['text']}_\n\n"
    elif broadcast_data["type"] == "photo":
        text += f"عکس + متن: {broadcast_data['caption'] or 'بدون متن'}\n\n"
    elif broadcast_data["type"] == "video":
        text += f"ویدیو + متن: {broadcast_data['caption'] or 'بدون متن'}\n\n"
    
    text += "برای تأیید گزینه زیر را بزنید:"
    
    keyboard = [
        [InlineKeyboardButton("✅ تأیید و ارسال", callback_data="broadcast_confirm")],
        [InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users - Admin only"""
    if not is_admin(update.effective_user.id):
        return
    
    # Check if message provided
    if not context.args:
        text = "📢 **ارسال پیام همگانی**\n\n"
        text += "**استفاده:**\n"
        text += "/broadcast پیام شما\n\n"
        text += "**مثال:**\n"
        text += "/broadcast سلام! سرور جدید اضافه شد 🎉"
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    # Get message
    message = " ".join(context.args)
    
    # Get all users
    users = await User.find_all().to_list()
    
    # Send confirmation
    confirm_text = f"📢 **تأیید ارسال**\n\n"
    confirm_text += f"پیام به {len(users)} کاربر ارسال میشود:\n\n"
    confirm_text += f"_{message}_\n\n"
    confirm_text += "برای تأیید /confirm را بزنید."
    
    # Store message in context
    context.user_data["broadcast_message"] = message
    context.user_data["broadcast_users"] = len(users)
    
    await update.message.reply_text(confirm_text, parse_mode="Markdown")


async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and send broadcast"""
    if not is_admin(update.effective_user.id):
        return
    
    message = context.user_data.get("broadcast_message")
    if not message:
        await update.message.reply_text("❌ پیامی برای ارسال وجود ندارد.")
        return
    
    # Get all users
    users = await User.find_all().to_list()
    
    # Send progress message
    progress_msg = await update.message.reply_text(
        f"⏳ در حال ارسال به {len(users)} کاربر...\n\n"
        f"ارسال شده: 0/{len(users)}"
    )
    
    # Send to all users
    success = 0
    failed = 0
    
    for i, user in enumerate(users):
        try:
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=f"📢 **اطلاعیه**\n\n{message}",
                parse_mode="Markdown"
            )
            success += 1
            
            # Update progress every 10 users
            if (i + 1) % 10 == 0:
                await progress_msg.edit_text(
                    f"⏳ در حال ارسال...\n\n"
                    f"ارسال شده: {i + 1}/{len(users)}\n"
                    f"✅ موفق: {success}\n"
                    f"❌ ناموفق: {failed}"
                )
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.05)
            
        except Exception as e:
            failed += 1
            print(f"Failed to send to {user.telegram_id}: {e}")
    
    # Final report
    await progress_msg.edit_text(
        f"✅ **ارسال کامل شد!**\n\n"
        f"📊 گزارش:\n"
        f"• کل: {len(users)}\n"
        f"• موفق: {success}\n"
        f"• ناموفق: {failed}"
    )
    
    # Clear context
    context.user_data.pop("broadcast_message", None)
    context.user_data.pop("broadcast_users", None)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics - Admin only"""
    if not is_admin(update.effective_user.id):
        return
    
    from app.models.order import Order, OrderStatus
    from app.models.subscription import Subscription
    from app.models.payment import Payment
    from datetime import datetime, timedelta
    
    # Time ranges
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)
    
    # Total stats
    total_users = await User.find_all().count()
    total_orders = await Order.find_all().count()
    total_subs = await Subscription.find({"is_active": True}).count()
    pending_payments = await Payment.find({"status": "pending"}).count()
    
    # Sales stats
    today_orders = await Order.find(
        Order.created_at >= today_start,
        Order.status == OrderStatus.PAID
    ).to_list()
    
    week_orders = await Order.find(
        Order.created_at >= week_start,
        Order.status == OrderStatus.PAID
    ).to_list()
    
    month_orders = await Order.find(
        Order.created_at >= month_start,
        Order.status == OrderStatus.PAID
    ).to_list()
    
    # Calculate revenue
    today_revenue = sum(o.price for o in today_orders)
    week_revenue = sum(o.price for o in week_orders)
    month_revenue = sum(o.price for o in month_orders)
    
    text = "📊 **آمار ربات**\n\n"
    text += f"👥 کاربران: {total_users}\n"
    text += f"📦 سفارشات: {total_orders}\n"
    text += f"✅ اشتراکهای فعال: {total_subs}\n"
    text += f"⏳ پرداختهای معلق: {pending_payments}\n\n"
    
    text += "💰 **فروش:**\n"
    text += f"📅 امروز: {len(today_orders)} فروش | {int(today_revenue / 1000):,} تومان\n"
    text += f"📆 7 روز: {len(week_orders)} فروش | {int(week_revenue / 1000):,} تومان\n"
    text += f"📆 30 روز: {len(month_orders)} فروش | {int(month_revenue / 1000):,} تومان\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def migrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Migrate users between panels - Admin only"""
    if not is_admin(update.effective_user.id):
        return
    
    if len(context.args) < 3:
        text = "🔄 **مهاجرت کاربران**\n\n"
        text += "**استفاده:**\n"
        text += "/migrate <source_panel> <target_panel> <max_users>\n\n"
        text += "**مثال:**\n"
        text += "/migrate Germany server2 10"
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    
    source_panel = context.args[0]
    target_panel = context.args[1]
    max_users = int(context.args[2])
    
    progress_msg = await update.message.reply_text(
        f"⏳ در حال مهاجرت {max_users} کاربر از {source_panel} به {target_panel}..."
    )
    
    try:
        from app.services.migration_service import migration_service
        result = await migration_service.migrate_users_from_panel(source_panel, target_panel, max_users)
        
        if result.get("success"):
            text = f"✅ **مهاجرت کامل شد!**\n\n"
            text += f"📊 گزارش:\n"
            text += f"• تلاش شده: {result['total_attempted']}\n"
            text += f"• موفق: {result['successful_migrations']}\n"
            text += f"• ناموفق: {result['failed_migrations']}"
        else:
            text = f"❌ **مهاجرت ناموفق:** {result.get('error')}"
        
        await progress_msg.edit_text(text, parse_mode="Markdown")
        
    except Exception as e:
        await progress_msg.edit_text(f"❌ خطا: {str(e)}")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعادل خودکار سرورها - Admin only"""
    if not is_admin(update.effective_user.id):
        return
    
    progress_msg = await update.message.reply_text(
        "⏳ در حال تعادل سرورها..."
    )
    
    try:
        from app.services.migration_service import migration_service
        result = await migration_service.auto_balance_panels()
        
        if result.get("success"):
            text = f"✅ **تعادل کامل شد!**\n\n"
            text += f"📊 گزارش:\n"
            text += f"• کل مهاجرتها: {result['total_migrations']}\n\n"
            
            for migration in result['migrations']:
                text += f"• {migration['from']} → {migration['to']}: {migration['attempted']} کاربر\n"
        else:
            text = f"❌ **تعادل ناموفق:** {result.get('error')}"
        
        await progress_msg.edit_text(text, parse_mode="Markdown")
        
    except Exception as e:
        await progress_msg.edit_text(f"❌ خطا: {str(e)}")


async def inbound_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show inbound load statistics - Admin only"""
    if not is_admin(update.effective_user.id):
        return
    
    from app.services.inbound_balancer import inbound_balancer
    from app.core.panel_config import panel_config
    
    progress_msg = await update.message.reply_text("⏳ در حال دریافت آمار inbound ها...")
    
    try:
        enabled_panels = panel_config.get_enabled_panels()
        text = "📊 **آمار Inbound ها**\n\n"
        
        for panel_key, panel_info in enabled_panels.items():
            stats = await inbound_balancer.get_inbound_load_stats(panel_key)
            
            if not stats:
                continue
            
            text += f"🏢 **{stats['panel_name']}** ({panel_info['flag']})\n"
            text += f"👥 کل کاربران: {stats['total_clients']}\n\n"
            
            if stats['tunnel_inbounds']:
                text += "🔗 **Tunnel Inbounds:**\n"
                for inbound in stats['tunnel_inbounds']:
                    text += f"  • ID {inbound['id']} ({inbound['protocol']}:{inbound['port']}): {inbound['client_count']} کاربر\n"
                text += "\n"
            
            if stats['direct_inbounds']:
                text += "🎯 **Direct Inbounds:**\n"
                for inbound in stats['direct_inbounds']:
                    text += f"  • ID {inbound['id']} ({inbound['protocol']}:{inbound['port']}): {inbound['client_count']} کاربر\n"
                text += "\n"
            
            text += "─" * 30 + "\n\n"
        
        await progress_msg.edit_text(text, parse_mode="Markdown")
        
    except Exception as e:
        await progress_msg.edit_text(f"❌ خطا: {str(e)}")
