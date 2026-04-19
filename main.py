import logging
import asyncio
from telegram import (
    Update, BotCommand,
    BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
)
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import TOKEN
from database import init_db
from handlers import (
    start, game_command, join_callback, start_early_callback,
    action_callback, bet_amount_callback, new_game_callback, profile_command,
    menu_callback, shop_callback, gold_buy_callback, chips_ad_callback, language_callback, daily_bonus_callback,
    help_command, private_text_router, language_command, leave_command, rules_command, issue_command,
    game_settings_callback, game_settings_value_callback, admin_command,
    inventory_command, inventory_callback, shop_command
)
from kaspi_handlers import (
    kaspi_callback, kaspi_receipt_photo_handler, admin_kaspi_callback, admin_kaspi_text_handler, admin_issues_callback
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
    
    logger.info("✅ Graceful shutdown complete")
    _shutdown_event.set()

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"📡 Received signal {signum}, initiating shutdown...")
    # Set the shutdown event to signal the main loop
    asyncio.create_task(_signal_async_shutdown())

async def _signal_async_shutdown():
    """Bridge between sync signal handler and async shutdown."""
    _shutdown_event.set()


async def post_init(application: Application):
    await init_db()
    ru_private_commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("profile", "Игровой профиль"),
        BotCommand("shop", "Магазин скинов"),
        BotCommand("inventory", "Инвентарь скинов"),
        BotCommand("language", "Выбрать язык"),
        BotCommand("leave", "Покинуть текущий стол"),
        BotCommand("rules", "Краткие правила"),
        BotCommand("issue", "Написать разработчику"),
        BotCommand("help", "Помощь"),
    ]
    en_private_commands = [
        BotCommand("start", "Start bot"),
        BotCommand("profile", "Game profile"),
        BotCommand("shop", "Skin shop"),
        BotCommand("inventory", "Skin inventory"),
        BotCommand("language", "Choose language"),
        BotCommand("leave", "Leave current table"),
        BotCommand("rules", "Quick rules"),
        BotCommand("issue", "Contact developer"),
        BotCommand("help", "Help"),
    ]
    ru_group_commands = [
        BotCommand("game", "Создать стол"),
        BotCommand("leave", "Покинуть стол"),
        BotCommand("help", "Помощь"),
    ]
    en_group_commands = [
        BotCommand("game", "Create table in group"),
        BotCommand("leave", "Leave table"),
        BotCommand("help", "Help"),
    ]
    await application.bot.set_my_commands(ru_private_commands, scope=BotCommandScopeAllPrivateChats(), language_code="ru")
    await application.bot.set_my_commands(en_private_commands, scope=BotCommandScopeAllPrivateChats(), language_code="en")
    await application.bot.set_my_commands(ru_group_commands, scope=BotCommandScopeAllGroupChats(), language_code="ru")
    await application.bot.set_my_commands(en_group_commands, scope=BotCommandScopeAllGroupChats(), language_code="en")
    print("🤖 Бот запущен и готов к игре!")


from telegram.error import RetryAfter

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, RetryAfter):
        logging.warning(f"Flood control exceeded. Retry in {context.error.retry_after} seconds.")
    else:
        logging.error(f"Exception while handling an update: {context.error}")

from telegram.error import NetworkError, RetryAfter, TimedOut

def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", game_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("leave", leave_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("issue", issue_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("inventory", inventory_command))

    # Игровые коллбэки (порядок важен!)
    application.add_handler(CallbackQueryHandler(join_callback, pattern="^join_game$"))
    application.add_handler(CallbackQueryHandler(start_early_callback, pattern="^start_early$"))
    application.add_handler(CallbackQueryHandler(action_callback, pattern="^action_"))
    application.add_handler(CallbackQueryHandler(bet_amount_callback, pattern="^bet_amount_"))
    application.add_handler(CallbackQueryHandler(new_game_callback, pattern="^new_game$"))
    application.add_handler(CallbackQueryHandler(game_settings_callback, pattern="^(set_blinds|set_seats)$"))
    application.add_handler(CallbackQueryHandler(game_settings_value_callback, pattern="^(blind_|seats_)"))

    # ЛС меню
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^(shop_|gold_exchange_|table_)"))
    application.add_handler(CallbackQueryHandler(gold_buy_callback, pattern="^gold_buy_"))
    application.add_handler(CallbackQueryHandler(chips_ad_callback, pattern="^chips_"))
    application.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^daily_bonus$"))
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(inventory_callback, pattern="^inv_"))

    # Kaspi Pay handlers
    application.add_handler(CallbackQueryHandler(kaspi_callback, pattern="^kaspi_"))
    application.add_handler(CallbackQueryHandler(admin_kaspi_callback, pattern="^admin_kaspi_|^admin_approve_|^admin_reject_|^admin_view_payment_|^admin_approve_comment_"))
    application.add_handler(CallbackQueryHandler(admin_issues_callback, pattern="^admin_issues|admin_view_issue_|admin_reply_issue_"))
    
    # Фото чеков Kaspi (высший приоритет в группе фото)
    application.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.PRIVATE,
        kaspi_receipt_photo_handler
    ))

    # Один роутер для всего текстового ввода в ЛС:
    # меню + ручной ввод ставки + админ комментарии Kaspi
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        private_text_router
    ))
    
    # Check if webhook mode is enabled
    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() == "true"
    webhook_url = os.getenv("WEBHOOK_URL", "")
    webhook_host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    # Railway provides PORT env var, use it if available
    webhook_port = int(os.getenv("PORT") or os.getenv("WEBHOOK_PORT", "8080"))
    
    if use_webhook and webhook_url:
        # Webhook mode (for production with reverse proxy)
        logger.info(f"🚀 Starting bot in WEBHOOK mode...")
        logger.info(f"   Webhook URL: {webhook_url}")
        
        async def run_webhook():
            from webhook_server import setup_webhook, remove_webhook
            from game_persistence import save_all_active_games, restore_saved_games, GamePersistence
            
            await application.initialize()
            await application.start()
            
            # Initialize game persistence tables
            await GamePersistence.init_tables()
            
            # Restore saved games on startup
            await restore_saved_games()
            
            # Setup webhook
            server = await setup_webhook(
                application,
                webhook_url=webhook_url,
                host=webhook_host,
                port=webhook_port
            )
            
            logger.info("🤖 Bot is running in webhook mode. Send SIGTERM to stop.")
            
            # Wait for shutdown
            await _shutdown_event.wait()
            
            # Graceful shutdown
            logger.info("🛑 Saving games before shutdown...")
            await save_all_active_games()
            await server.stop()
            await remove_webhook(application)
            await graceful_shutdown(application)
        
        asyncio.run(run_webhook())
    else:
        # Polling mode (default, for development)
        logger.info(f"🚀 Starting bot in POLLING mode...")
        
        import time
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"   Attempt {attempt + 1}/{max_retries}")
                
                async def run_polling():
                    from game_persistence import save_all_active_games, restore_saved_games, GamePersistence
                    
                    await application.initialize()
                    await application.start()
                    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                    
                    # Initialize game persistence tables
                    await GamePersistence.init_tables()
                    
                    # Restore saved games on startup
                    await restore_saved_games()
                    
                    logger.info("🤖 Bot is running. Press Ctrl+C to stop.")
                    
                    # Wait for shutdown signal
                    await _shutdown_event.wait()
                    
                    # Save games before shutdown
                    logger.info("🛑 Saving games before shutdown...")
                    await save_all_active_games()
                    
                    # Perform graceful shutdown
                    await graceful_shutdown(application)
                
                asyncio.run(run_polling())
                break  # If we get here, shutdown was graceful
                
            except NetworkError as e:
                logger.warning(f"⚠️ Network error: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)
                else:
                    logger.error("❌ Max retries reached.")
                    raise
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                raise


def validate_config():
    """Validate configuration before starting."""
    import os
    errors = []
    
    # Check token
    if not TOKEN or TOKEN == 'your_bot_token_here':
        errors.append("POKER_BOT_TOKEN not set! Get it from @BotFather")
    
    # Check admin IDs
    admin_ids = os.getenv('POKER_ADMIN_IDS', '')
    if not admin_ids or admin_ids == 'your_admin_id_here':
        errors.append("POKER_ADMIN_IDS not set!")
    
    # Check webhook config
    use_webhook = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
    if use_webhook:
        webhook_url = os.getenv('WEBHOOK_URL', '')
        if not webhook_url:
            errors.append("USE_WEBHOOK=true but WEBHOOK_URL is empty!")
        elif not webhook_url.startswith('https://'):
            errors.append(f"WEBHOOK_URL must start with https:// (got: {webhook_url})")
        elif not webhook_url.endswith('/webhook'):
            logger.warning("WEBHOOK_URL should end with /webhook")
    
    if errors:
        logger.error("❌ Configuration errors:")
        for err in errors:
            logger.error(f"   - {err}")
        logger.error("\nSet these in Railway Dashboard → Variables")
        return False
    
    return True


if __name__ == '__main__':
    # Validate before starting
    if not validate_config():
        sys.exit(1)
    
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error starting bot")
        sys.exit(1)
