import logging
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
    kaspi_callback, kaspi_receipt_photo_handler, admin_kaspi_callback, admin_kaspi_text_handler
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").disabled = True


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
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^shop_"))
    application.add_handler(CallbackQueryHandler(gold_buy_callback, pattern="^gold_buy_"))
    application.add_handler(CallbackQueryHandler(chips_ad_callback, pattern="^chips_"))
    application.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^daily_bonus$"))
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(inventory_callback, pattern="^inv_"))

    # Kaspi Pay handlers
    application.add_handler(CallbackQueryHandler(kaspi_callback, pattern="^kaspi_"))
    application.add_handler(CallbackQueryHandler(admin_kaspi_callback, pattern="^admin_kaspi_|^admin_approve_|^admin_reject_"))
    
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
    
    # Run with retry logic for network errors
    import asyncio
    import time
    
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            print(f"🚀 Starting bot... (attempt {attempt + 1}/{max_retries})")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            break  # If successful, exit loop
        except NetworkError as e:
            print(f"⚠️ Network error: {e}")
            if attempt < max_retries - 1:
                print(f"⏳ Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s
            else:
                print("❌ Max retries reached. Please check your internet connection.")
                raise
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            raise


if __name__ == "__main__":
    if not TOKEN:
        print("ОШИБКА: POKER_BOT_TOKEN не задан. Укажи его в переменных окружения.")
        exit(1)
    main()
