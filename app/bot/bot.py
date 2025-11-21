import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from app.core.config import settings
from app.bot.handlers.start import start_handler, button_handler
from app.services.vpn_service import vpn_service

class TelegramBot:
    def __init__(self):
        self.application = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .pool_timeout(30.0)
            .get_updates_connect_timeout(30.0)
            .get_updates_read_timeout(30.0)
            .build()
        )
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup bot command and callback handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", start_handler))
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("status", self._status_command))
        self.application.add_handler(CommandHandler("restart", self._restart_command))
        
        # Admin commands
        from app.bot.handlers.admin import broadcast_command, confirm_broadcast, stats_command, admin_panel
        self.application.add_handler(CommandHandler("broadcast", broadcast_command))
        self.application.add_handler(CommandHandler("confirm", confirm_broadcast))
        self.application.add_handler(CommandHandler("stats", stats_command))
        self.application.add_handler(CommandHandler("admin", admin_panel))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(button_handler))
        
        # Message handler for reply keyboard buttons
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_reply_keyboard))
        
        # Photo handler for payment proofs
        self.application.add_handler(MessageHandler(filters.PHOTO, self._handle_payment_photo))
        
        # Video/media handler for broadcast
        self.application.add_handler(MessageHandler(filters.VIDEO | filters.FORWARDED, self._handle_media))
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        text = "ℹ️ **راهنمای ربات VPN**\n\n"
        text += "📋 **دستورات موجود:**\n"
        text += "/start - منوی اصلی\n"
        text += "/help - نمایش این راهنما\n"
        text += "/status - وضعیت ربات\n\n"
        text += "🤖 از گزینه‌ها برای حرکت استفاده کنید!"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        text = "📊 **وضعیت ربات**\n\n"
        text += "✅ ربات در حال اجرا است\n"
        text += f"🌍 پنلها: {len(vpn_service.ENABLED_PANELS)}\n"
        text += f"🔧 پروتکلها: تشخیص خودکار (VLESS, Trojan, VMess, و غیره)\n"
        text += f"📱 سیستم چند پنله فعال\n\n"
        text += "از /start برای شروع استفاده کنید!"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def _handle_reply_keyboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle reply keyboard button presses"""
        text = update.message.text
        
        if "خرید VPN" in text:
            from app.bot.handlers.start import show_protocol_selection_message
            await show_protocol_selection_message(update)
        elif "اشتراک من" in text:
            from app.bot.handlers.start import show_my_subscription_message
            await show_my_subscription_message(update)
        elif "کانفیگ های من" in text:
            from app.bot.handlers.start import show_my_configs_message
            await show_my_configs_message(update)
        elif "فاکتور های من" in text:
            from app.bot.handlers.start import show_my_orders_message
            await show_my_orders_message(update)
        elif "راهنما" in text:
            from app.bot.handlers.start import show_help_message
            await show_help_message(update)
        elif "شروع مجدد" in text:
            from app.bot.handlers.start import restart_bot_message
            await restart_bot_message(update, context)
        else:
            # Check if user is entering config name
            if context.user_data.get("waiting_for_config_name"):
                from app.bot.handlers.start import handle_config_name_input
                await handle_config_name_input(update, context)
            # Check if admin is entering broadcast message
            elif context.user_data.get("waiting_for_broadcast"):
                from app.bot.handlers.admin import handle_broadcast_message
                await handle_broadcast_message(update, context)
            else:
                text = "🤖 من این پیام را نمیفهمم.\n\n"
                text += "از گزینههای زیر استفاده کنید!"
                await update.message.reply_text(text)
    
    async def _handle_payment_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle payment proof photos"""
        from app.models.payment import Payment
        from app.services.payment_service import payment_service
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        if not update.effective_user:
            return
        
        # Check if admin is sending broadcast photo
        if context.user_data.get("waiting_for_broadcast"):
            from app.bot.handlers.admin import handle_broadcast_message
            await handle_broadcast_message(update, context)
            return
        
        user_id = update.effective_user.id
        photo = update.message.photo[-1]  # Get highest resolution
        caption = update.message.caption or ""
        
        # Check if user has a pending payment AND is waiting for photo
        payment = await Payment.find_one({
            "user_telegram_id": user_id,
            "status": "pending",
            "payment_proof_file_id": None  # Only accept if no proof submitted yet
        })
        
        if not payment:
            await update.message.reply_text(
                "❌ **عکس نامعتبر**\n\n"
                "شما هیچ پرداخت معلقی ندارید یا قبلاً رسید ارسال کردهاید.\n\n"
                "برای خرید VPN از گزینه 🛒 خرید VPN استفاده کنید.",
                parse_mode="Markdown"
            )
            return
        
        # Save payment proof
        await payment_service.submit_payment_proof(payment, photo.file_id, caption)
        
        # Send to payment channel for admin review
        keyboard = [
            [
                InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_payment_{payment.id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Get user info
        from app.models.user import User
        user = await User.find_one(User.telegram_id == user_id)
        
        username_display = f"@{user.username}" if user.username else "N/A"
        phone_display = user.phone if user.phone else "N/A"
        amount_display = int(payment.amount / 1000)
        admin_text = f"💳 **درخواست تأیید پرداخت**\n\n"
        admin_text += f"👤 **کاربر:** {user.first_name}\n"
        admin_text += f"💬 **یوزرنیم:** {username_display}\n"
        admin_text += f"📱 **تلفن:** {phone_display}\n"
        admin_text += f"🆔 **ID:** `{user.telegram_id}`\n"
        admin_text += f"💰 **مبلغ:** {amount_display}تومان\n"
        admin_text += f"💳 **روش:** {payment.payment_method}\n"
        if caption:
            admin_text += f"📝 **پیام:** {caption}\n"
        admin_text += f"🕰 **زمان:** {payment.created_at.strftime('%Y-%m-%d %H:%M')}"
        
        # Send to payment channel
        admin_message = await context.bot.send_photo(
            chat_id=settings.PAYMENT_CHANNEL_ID,
            photo=photo.file_id,
            caption=admin_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # Save admin message ID
        payment.admin_message_id = admin_message.message_id
        await payment.save()
        
        # Confirm to user
        await update.message.reply_text(
            "✅ **رسید دریافت شد!**\n\n"
            "🕰 رسید پرداخت شما به ادمین ارسال شد.\n"
            "⏰ منتظر تأیید باشید (حداکثر 2 ساعت).\n\n"
            "✅ پس از تأیید، کانفیگ VPN ارسال میشود.",
            parse_mode="Markdown"
        )
    
    async def _handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video and forwarded messages for broadcast"""
        if not update.effective_user:
            return
        
        # Check if admin is waiting for broadcast message
        if context.user_data.get("waiting_for_broadcast"):
            from app.bot.handlers.admin import handle_broadcast_message
            await handle_broadcast_message(update, context)
        
    async def _set_bot_commands(self):
        """Set bot menu commands""" 
        from telegram import BotCommand
        
        commands = [
            BotCommand("start", "منوی اصلی و شروع ربات"),
            BotCommand("help", "راهنمای استفاده از ربات"),
            BotCommand("status", "وضعیت ربات و پنل‌ها"),
            BotCommand("restart", "شروع مجدد و بازگشت به منوی اصلی"),
        ]
        await self.application.bot.set_my_commands(commands)
        
        # Set bot description and short description
        if settings.BOT_DESCRIPTION:
            description = settings.BOT_DESCRIPTION.replace('\\n', '\n')
            await self.application.bot.set_my_description(description)
        if settings.BOT_SHORT_DESCRIPTION:
            short_desc = settings.BOT_SHORT_DESCRIPTION.replace('\\n', '\n')
            await self.application.bot.set_my_short_description(short_desc)
        
    async def _restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /restart command - same as /start"""
        await start_handler(update, context)

    
    async def start(self):
        """Start the bot"""
        print("🤖 Starting VPN Bot...")
        await self.application.initialize()
        await self.application.start()
        await self._set_bot_commands()
        
        # Start background tasks (only in production)
        import os
        if os.getenv("ENVIRONMENT", "development") == "production":
            from app.services.payment_expiry_checker import check_expired_payments, check_expired_subscriptions
            from app.services.abandoned_cart_reminder import check_abandoned_carts
            asyncio.create_task(check_expired_payments(self.application.bot))
            asyncio.create_task(check_expired_subscriptions(self.application.bot))
            asyncio.create_task(check_abandoned_carts(self.application.bot))
            print("✅ Background tasks started")
        else:
            print("⚠️ Background tasks disabled in development mode")
        
        print("✅ Bot started successfully!")
        await self.application.updater.start_polling()
    
    async def stop(self):
        """Stop the bot"""
        print("🛑 Stopping VPN Bot...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        print("✅ Bot stopped successfully!")

# Global bot instance
bot = TelegramBot()