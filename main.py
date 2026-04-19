import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import TOKEN
from database import init_db
from handlers import (
    start, game_command, join_callback, start_early_callback,
    action_callback, bet_amount_callback, new_game_callback, profile_command,
    menu_callback, shop_callback, gold_buy_callback, chips_ad_callback, language_callback, daily_bonus_callback,
    help_command, private_text_router, language_command, leave_command, rules_command, issue_command,
    game_settings_callback, game_settings_value_callback, admin_command,
    inventory_command, inventory_callback, shop_command,
    ban_command, unban_command, finduser_command, broadcast_command, checkuser_command
)
from kaspi_handlers import (
    kaspi_callback, kaspi_receipt_photo_handler, admin_kaspi_callback, admin_kaspi_text_handler, admin_issues_callback
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    # Initialize database (run async init_db in temporary event loop)
    import asyncio
    asyncio.run(init_db())
    
    # Create application
    application = Application.builder().token(TOKEN).build()

    # === COMMANDS ===
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("game", game_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("inventory", inventory_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("leave", leave_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("issue", issue_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("shop", shop_command))
    
    # === ADMIN COMMANDS ===
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("finduser", finduser_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("checkuser", checkuser_command))

    # === CALLBACKS ===
    # Game
    application.add_handler(CallbackQueryHandler(join_callback, pattern="^join_game$"))
    application.add_handler(CallbackQueryHandler(start_early_callback, pattern="^start_early$"))
    application.add_handler(CallbackQueryHandler(action_callback, pattern="^action_"))
    application.add_handler(CallbackQueryHandler(action_callback, pattern="^(confirm_all_in|cancel_all_in)$"))
    application.add_handler(CallbackQueryHandler(bet_amount_callback, pattern="^bet_amount_"))
    application.add_handler(CallbackQueryHandler(new_game_callback, pattern="^new_game$"))
    application.add_handler(CallbackQueryHandler(game_settings_callback, pattern="^(set_blinds|set_seats)$"))
    application.add_handler(CallbackQueryHandler(game_settings_value_callback, pattern="^(blind_|seats_)"))

    # Menu & Shop
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^(shop_|gold_exchange_|table_)"))
    application.add_handler(CallbackQueryHandler(gold_buy_callback, pattern="^gold_buy_"))
    application.add_handler(CallbackQueryHandler(chips_ad_callback, pattern="^chips_"))
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^daily_bonus$"))
    application.add_handler(CallbackQueryHandler(inventory_callback, pattern="^inv_"))

    # Kaspi
    application.add_handler(CallbackQueryHandler(kaspi_callback, pattern="^kaspi_"))
    application.add_handler(CallbackQueryHandler(admin_kaspi_callback, pattern="^admin_kaspi_|^admin_approve_|^admin_reject_|^admin_view_payment_|^admin_approve_comment_"))
    application.add_handler(CallbackQueryHandler(admin_issues_callback, pattern="^admin_issues|admin_view_issue_|admin_reply_issue_"))

    # === MESSAGE HANDLERS ===
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, kaspi_receipt_photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_router))

    logger.info("🤖 Bot started!")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
