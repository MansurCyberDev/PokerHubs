import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from aiohttp import web

from config import TOKEN, ADMIN_IDS
from database import init_db, is_user_banned
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


async def check_banned_middleware(update: Update, context) -> bool:
    """Middleware to check if user is banned. Returns True if banned, False otherwise."""
    user_id = None
    chat_id = None
    
    # Get user_id from different update types
    if update.effective_user:
        user_id = update.effective_user.id
    elif update.message and update.message.from_user:
        user_id = update.message.from_user.id
    elif update.callback_query and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id
    
    if not user_id:
        return False
    
    # Admins are never banned
    if user_id in ADMIN_IDS:
        return False
    
    # Check if user is banned
    try:
        if await is_user_banned(user_id):
            chat_id = update.effective_chat.id if update.effective_chat else None
            
            # Send ban message
            ban_message = (
                "🚫 <b>Вы забанены в PokerHubs</b>\n"
                "════════════════════\n\n"
                "Вы не можете использовать функции бота.\n\n"
                "Для разбана обратитесь к администрации."
            )
            
            try:
                if chat_id:
                    await context.bot.send_message(chat_id, ban_message, parse_mode="HTML")
            except Exception:
                pass
            
            return True
    except Exception as e:
        logger.error(f"Error checking ban status: {e}")
    
    return False


async def banned_command_handler(update: Update, context):
    """Handler that blocks commands for banned users."""
    if await check_banned_middleware(update, context):
        return


async def banned_callback_handler(update: Update, context):
    """Handler that blocks callbacks for banned users."""
    if await check_banned_middleware(update, context):
        try:
            await update.callback_query.answer("🚫 Вы забанены!", show_alert=True)
        except Exception:
            pass
        return


async def async_main():
    # Initialize database
    await init_db()
    
    # Create application
    application = Application.builder().token(TOKEN).build()

    # === BAN CHECK MIDDLEWARE (High priority - must be first) ===
    # Add type handlers that check bans before processing
    application.add_handler(MessageHandler(filters.COMMAND, banned_command_handler), group=0)
    application.add_handler(CallbackQueryHandler(banned_callback_handler, pattern=".*"), group=0)

    # === COMMANDS (Group 1 - after ban check) ===
    application.add_handler(CommandHandler("start", start), group=1)
    application.add_handler(CommandHandler("game", game_command), group=1)
    application.add_handler(CommandHandler("profile", profile_command), group=1)
    application.add_handler(CommandHandler("inventory", inventory_command), group=1)
    application.add_handler(CommandHandler("help", help_command), group=1)
    application.add_handler(CommandHandler("language", language_command), group=1)
    application.add_handler(CommandHandler("leave", leave_command), group=1)
    application.add_handler(CommandHandler("rules", rules_command), group=1)
    application.add_handler(CommandHandler("issue", issue_command), group=1)
    application.add_handler(CommandHandler("admin", admin_command), group=1)
    application.add_handler(CommandHandler("shop", shop_command), group=1)
    
    # === ADMIN COMMANDS (Group 1 - ban/unban always work for admins) ===
    application.add_handler(CommandHandler("ban", ban_command), group=1)
    application.add_handler(CommandHandler("unban", unban_command), group=1)
    application.add_handler(CommandHandler("finduser", finduser_command), group=1)
    application.add_handler(CommandHandler("broadcast", broadcast_command), group=1)
    application.add_handler(CommandHandler("checkuser", checkuser_command), group=1)

    # === CALLBACKS (Group 1 - after ban check) ===
    # Game
    application.add_handler(CallbackQueryHandler(join_callback, pattern="^join_game$"), group=1)
    application.add_handler(CallbackQueryHandler(start_early_callback, pattern="^start_early$"), group=1)
    application.add_handler(CallbackQueryHandler(action_callback, pattern="^action_"), group=1)
    application.add_handler(CallbackQueryHandler(action_callback, pattern="^(confirm_all_in|cancel_all_in)$"), group=1)
    application.add_handler(CallbackQueryHandler(bet_amount_callback, pattern="^bet_amount_"), group=1)
    application.add_handler(CallbackQueryHandler(new_game_callback, pattern="^new_game$"), group=1)
    application.add_handler(CallbackQueryHandler(game_settings_callback, pattern="^(set_blinds|set_seats)$"), group=1)
    application.add_handler(CallbackQueryHandler(game_settings_value_callback, pattern="^(blind_|seats_)"), group=1)

    # Menu & Shop
    application.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"), group=1)
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^(shop_|gold_exchange_|table_)"), group=1)
    application.add_handler(CallbackQueryHandler(gold_buy_callback, pattern="^gold_buy_"), group=1)
    application.add_handler(CallbackQueryHandler(chips_ad_callback, pattern="^chips_"), group=1)
    application.add_handler(CallbackQueryHandler(language_callback, pattern="^lang_"), group=1)
    application.add_handler(CallbackQueryHandler(daily_bonus_callback, pattern="^daily_bonus$"), group=1)
    application.add_handler(CallbackQueryHandler(inventory_callback, pattern="^inv_"), group=1)

    # Kaspi
    application.add_handler(CallbackQueryHandler(kaspi_callback, pattern="^kaspi_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_kaspi_callback, pattern="^admin_kaspi_|^admin_approve_|^admin_reject_|^admin_view_payment_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_issues_callback, pattern="^(admin_issues|admin_view_issue_|admin_reply_issue_)"), group=1)

    # === MESSAGE HANDLERS (Group 1 - after ban check) ===
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, kaspi_receipt_photo_handler), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_router), group=1)

    logger.info("🤖 Bot started!")
    
    # Start polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    # Start HTTP health server for Render
    async def health_handler(request):
        return web.Response(text='OK', status=200)
    
    app = web.Application()
    app.router.add_get('/healthz', health_handler)
    app.router.add_get('/', health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("🌐 Health server started on port 10000")
    
    # Keep the bot running
    while True:
        await asyncio.sleep(3600)


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")


if __name__ == '__main__':
    main()
