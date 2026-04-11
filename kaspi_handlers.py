from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from handlers import _user_lang
from keyboards import get_admin_kaspi_panel_keyboard, get_admin_payment_action_keyboard, get_admin_payment_view_keyboard

# ==================== KASPI PAY HANDLERS ====================

# Kaspi payment prices mapping - GOLD ONLY (chips are bought with gold)
KASPI_PRICES = {
    # Gold packages - по запросу пользователя
    "gold_100": {"amount": 100, "price_kzt": 100, "name": "100 Gold"},
    "gold_200": {"amount": 200, "price_kzt": 150, "name": "200 Gold"},
    "gold_300": {"amount": 300, "price_kzt": 200, "name": "300 Gold"},
    "gold_500": {"amount": 500, "price_kzt": 300, "name": "500 Gold (экономия 100₸)"},
    "gold_1000": {"amount": 1000, "price_kzt": 550, "name": "1000 Gold (экономия 450₸)"},
    "gold_2000": {"amount": 2000, "price_kzt": 1000, "name": "2000 Gold (экономия 1000₸)"},
    # Фишки через Kaspi (альтернативный способ)
    "chips_10k": {"amount": 10000, "price_kzt": 100, "name": "10 000 фишек"},
    "chips_25k": {"amount": 25000, "price_kzt": 150, "name": "25 000 фишек"},
    "chips_50k": {"amount": 50000, "price_kzt": 250, "name": "50 000 фишек"},
}

# User state for pending receipt uploads
kaspi_pending_receipts = {}  # user_id -> payment_id


async def kaspi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Kaspi Pay callbacks - chips and gold packages."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    lang = await _user_lang(user.id)
    is_en = lang == "en"
    data = query.data

    # Map callback data to item info (item_type, item_id, amount_item, amount_kzt)
    item_map = {
        # Gold packages
        "kaspi_gold_100": ("gold", "gold_100", 100, 100),
        "kaspi_gold_200": ("gold", "gold_200", 200, 150),
        "kaspi_gold_300": ("gold", "gold_300", 300, 200),
        "kaspi_gold_500": ("gold", "gold_500", 500, 300),
        "kaspi_gold_1000": ("gold", "gold_1000", 1000, 550),
        "kaspi_gold_2000": ("gold", "gold_2000", 2000, 1000),
        # Chips via Kaspi (direct)
        "kaspi_chips_10k": ("chips", "chips_10k", 10000, 100),
        "kaspi_chips_25k": ("chips", "chips_25k", 25000, 150),
        "kaspi_chips_50k": ("chips", "chips_50k", 50000, 250),
    }

    # Handle menu navigation
    if data == "kaspi_chips_menu":
        text = (
            f"💳 <b>KASPI PAY — ФИШКИ</b>\n"
            f"════════════════════\n\n"
            f"Выбери пакет фишек для покупки:\n\n"
            f"💰 Оплата через Kaspi (Казахстан)\n"
            f"📱 Перевод на номер +77012345678\n"
            f"⏰ Подтверждение 5-30 минут"
        ) if not is_en else (
            f"💳 <b>KASPI PAY — CHIPS</b>\n"
            f"════════════════════\n\n"
            f"Choose chip package:\n\n"
            f"💰 Payment via Kaspi (Kazakhstan)\n"
            f"📱 Transfer to +77012345678\n"
            f"⏰ Confirmation 5-30 minutes"
        )
        
        from keyboards import get_kaspi_chips_packages_keyboard
        await query.edit_message_text(
            text,
            reply_markup=get_kaspi_chips_packages_keyboard(lang),
            parse_mode=ParseMode.HTML
        )
        return
    
    if data == "kaspi_gold_menu":
        text = (
            f"💳 <b>KASPI PAY — GOLD</b>\n"
            f"════════════════════\n\n"
            f"Выбери пакет Gold для покупки:\n\n"
            f"💰 Оплата через Kaspi (Казахстан)\n"
            f"📱 Перевод на номер +77012345678\n"
            f"⏰ Подтверждение 5-30 минут"
        ) if not is_en else (
            f"💳 <b>KASPI PAY — GOLD</b>\n"
            f"════════════════════\n\n"
            f"Choose Gold package:\n\n"
            f"💰 Payment via Kaspi (Kazakhstan)\n"
            f"📱 Transfer to +77012345678\n"
            f"⏰ Confirmation 5-30 minutes"
        )
        
        from keyboards import get_kaspi_gold_packages_keyboard
        await query.edit_message_text(
            text,
            reply_markup=get_kaspi_gold_packages_keyboard(lang),
            parse_mode=ParseMode.HTML
        )
        return

    if data in item_map:
        item_type, item_id, amount_item, amount_kzt = item_map[data]
        
        # Create payment in database
        from database import create_kaspi_payment
        payment_id = await create_kaspi_payment(
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
            item_type=item_type,
            item_id=item_id,
            amount_kzt=amount_kzt,
            amount_item=amount_item
        )
        
        # Get item name
        item_name = KASPI_PRICES.get(item_id, {}).get("name", item_id)
        
        # Show payment instructions
        instruction_text = (
            f"💳 <b>KASPI PAY</b>\n"
            f"════════════════════\n\n"
            f"📦 <b>{item_name}</b>\n"
            f"💰 <b>Сумма: {amount_kzt} ₸</b>\n\n"
            f"<b>Инструкция по оплате:</b>\n\n"
            f"1️⃣ Открой приложение Kaspi\n"
            f"2️⃣ Нажми «Переводы»\n"
            f"3️⃣ Введи номер: <code>+77012345678</code>\n"
            f"4️⃣ Укажи сумму: <b>{amount_kzt} ₸</b>\n"
            f"5️⃣ В комментарии напиши:\n"
            f"<code>PAY{payment_id}</code>\n\n"
            f"6️⃣ После оплаты нажми кнопку ниже и пришли фото чека\n\n"
            f"⏰ Заявка активна 24 часа\n"
            f"ID: <code>#{payment_id}</code>"
        ) if not is_en else (
            f"💳 <b>KASPI PAY</b>\n"
            f"════════════════════\n\n"
            f"📦 <b>{item_name}</b>\n"
            f"💰 <b>Amount: {amount_kzt} ₸</b>\n\n"
            f"<b>Payment Instructions:</b>\n\n"
            f"1️⃣ Open Kaspi app\n"
            f"2️⃣ Tap «Transfers»\n"
            f"3️⃣ Enter number: <code>+77012345678</code>\n"
            f"4️⃣ Amount: <b>{amount_kzt} ₸</b>\n"
            f"5️⃣ In comment write:\n"
            f"<code>PAY{payment_id}</code>\n\n"
            f"6️⃣ After payment tap button below and send receipt photo\n\n"
            f"⏰ Active for 24 hours\n"
            f"ID: <code>#{payment_id}</code>"
        )
        
        from keyboards import get_kaspi_payment_instruction_keyboard
        await query.edit_message_text(
            instruction_text,
            reply_markup=get_kaspi_payment_instruction_keyboard(payment_id, lang),
            parse_mode=ParseMode.HTML
        )
        
        # Admin will be notified only after user uploads receipt
        
    elif data.startswith("kaspi_upload_"):
        payment_id = int(data.replace("kaspi_upload_", ""))
        kaspi_pending_receipts[user.id] = payment_id
        
        text = (
            "📤 <b>ОТПРАВКА ЧЕКА</b>\n"
            "════════════════════\n\n"
            "Пришли фото чека из приложения Kaspi.\n\n"
            "✅ Чек должен показывать:\n"
            "• Сумму перевода\n"
            "• Время операции\n"
            "• Номер получателя\n\n"
            "❌ Не принимаются:\n"
            "• Скриншоты экрана\n"
            "• Фото с других устройств"
        ) if not is_en else (
            "📤 <b>UPLOAD RECEIPT</b>\n"
            "════════════════════\n\n"
            "Send a photo of the Kaspi receipt.\n\n"
            "✅ Receipt must show:\n"
            "• Transfer amount\n"
            "• Transaction time\n"
            "• Recipient number\n\n"
            "❌ Not accepted:\n"
            "• Screenshots\n"
            "• Photos from other devices"
        )
        
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        
    elif data.startswith("kaspi_cancel_"):
        payment_id = int(data.replace("kaspi_cancel_", ""))
        
        text = (
            "❌ <b>ЗАЯВКА ОТМЕНЕНА</b>\n\n"
            "Если ты уже оплатил — не переживай!\n"
            "Пришли чек и админ всё проверит."
        ) if not is_en else (
            "❌ <b>PAYMENT CANCELLED</b>\n\n"
            "If you already paid — don't worry!\n"
            "Send the receipt and admin will check."
        )
        
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        
        # Remove from pending uploads if exists
        if user.id in kaspi_pending_receipts:
            del kaspi_pending_receipts[user.id]


async def kaspi_receipt_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle receipt photo uploads from users."""
    user = update.effective_user
    
    # Check if user has pending receipt upload
    if user.id not in kaspi_pending_receipts:
        # Ignore photos not related to Kaspi payments
        return
    
    payment_id = kaspi_pending_receipts[user.id]
    lang = await _user_lang(user.id)
    is_en = lang == "en"
    
    # Get photo file_id (best quality)
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    # Save receipt to payment
    from database import add_receipt_to_payment, get_kaspi_payment
    await add_receipt_to_payment(payment_id, file_id)
    
    # Get payment info
    payment = await get_kaspi_payment(payment_id)
    
    # Confirm to user
    text = (
        "✅ <b>ЧЕК ПОЛУЧЕН!</b>\n\n"
        f"Заявка #{payment_id} отправлена на проверку.\n"
        "Обычно проверка занимает 5-30 минут.\n\n"
        "Ты получишь уведомление после одобрения."
    ) if not is_en else (
        "✅ <b>RECEIPT RECEIVED!</b>\n\n"
        f"Payment #{payment_id} sent for review.\n"
        "Usually takes 5-30 minutes.\n\n"
        "You'll be notified after approval."
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    # Remove from pending uploads
    del kaspi_pending_receipts[user.id]
    
    # Notify admins about receipt with full payment details
    await notify_admins_receipt_received(context, payment_id, user, file_id, payment)


async def notify_admins_new_payment(context: ContextTypes.DEFAULT_TYPE, payment_id: int, 
                                     user, item_name: str, amount_kzt: int):
    """Notify all admins about new payment request."""
    from config import ADMIN_IDS
    
    text = (
        f"🔔 <b>НОВАЯ ЗАЯВКА КАСПИ</b>\n\n"
        f"ID: <code>#{payment_id}</code>\n"
        f"Пользователь: {user.first_name} (@{user.username or 'no_username'})\n"
        f"User ID: <code>{user.id}</code>\n\n"
        f"📦 Товар: <b>{item_name}</b>\n"
        f"💰 Сумма: <b>{amount_kzt} ₸</b>\n\n"
        f"Статус: ⏳ Ожидает оплаты"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")


async def notify_admins_receipt_received(context: ContextTypes.DEFAULT_TYPE, payment_id: int,
                                        user, receipt_file_id: str, payment: dict):
    """Notify admins that user uploaded receipt with full payment details."""
    from config import ADMIN_IDS
    from keyboards import get_admin_payment_view_keyboard
    
    item_name = KASPI_PRICES.get(payment['item_id'], {}).get("name", payment['item_id'])
    
    text = (
        f"🔔 <b>НОВАЯ ЗАЯВКА КАСПИ</b>\n"
        f"════════════════════\n\n"
        f"📋 <b>Номер заявки:</b> <code>#{payment_id}</code>\n"
        f"👤 <b>Пользователь:</b> {user.first_name}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"📱 <b>Telegram:</b> @{user.username or 'нет_username'}\n\n"
        f"📦 <b>Товар:</b> {item_name}\n"
        f"💰 <b>Сумма к оплате:</b> {payment['amount_kzt']} ₸\n\n"
        f"✅ Требуется проверка!\n"
        f"📎 Чек будет показан при просмотре заявки"
    )
    
    # Store message IDs for deletion later and receipt file_id
    if 'admin_payment_notifications' not in context.bot_data:
        context.bot_data['admin_payment_notifications'] = {}
    if 'payment_receipts' not in context.bot_data:
        context.bot_data['payment_receipts'] = {}
    
    # Store receipt file_id for later use
    context.bot_data['payment_receipts'][payment_id] = receipt_file_id
    
    for admin_id in ADMIN_IDS:
        try:
            # Send notification only (without receipt photo)
            msg = await context.bot.send_message(
                admin_id,
                text,
                reply_markup=get_admin_payment_view_keyboard(payment_id),
                parse_mode=ParseMode.HTML
            )
            # Store message ID for this admin
            if payment_id not in context.bot_data['admin_payment_notifications']:
                context.bot_data['admin_payment_notifications'][payment_id] = {}
            context.bot_data['admin_payment_notifications'][payment_id][admin_id] = {
                'message_id': msg.message_id
            }
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")


async def admin_kaspi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin Kaspi panel callbacks."""
    query = update.callback_query
    user = update.effective_user
    
    # Check if user is admin
    from config import ADMIN_IDS
    if user.id not in ADMIN_IDS:
        await query.answer("⛔ Только для админов!", show_alert=True)
        return
    
    data = query.data
    lang = await _user_lang(user.id)
    is_en = lang == "en"
    
    if data == "admin_kaspi_pending":
        # Show pending payments list
        from database import get_pending_payments
        from keyboards import get_admin_pending_list_keyboard
        pending = await get_pending_payments()
        
        if not pending:
            await query.edit_message_text(
                "✅ Нет ожидающих заявок" if not is_en else "✅ No pending payments",
                reply_markup=get_admin_kaspi_panel_keyboard(lang)
            )
            return
        
        # Show list of pending payments as buttons
        text = (
            f"📋 <b>ОЖИДАЮЩИЕ ЗАЯВКИ</b>\n"
            f"════════════════════\n\n"
            f"Всего: <b>{len(pending)}</b>\n\n"
            f"Выберите заявку для просмотра:"
            if not is_en else
            f"📋 <b>PENDING PAYMENTS</b>\n"
            f"════════════════════\n\n"
            f"Total: <b>{len(pending)}</b>\n\n"
            f"Select a payment to view:"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=get_admin_pending_list_keyboard(pending, lang),
            parse_mode=ParseMode.HTML
        )
        
    elif data == "admin_kaspi_stats":
        # Show payment statistics
        from database import get_payment_stats
        stats = await get_payment_stats()
        
        text = (
            f"📊 <b>СТАТИСТИКА ПЛАТЕЖЕЙ</b>\n"
            f"════════════════════\n\n"
            f"📋 Всего заявок: <b>{stats['total']}</b>\n"
            f"⏳ Ожидают: <b>{stats['pending']}</b>\n"
            f"✅ Одобрено: <b>{stats['approved']}</b>\n"
            f"❌ Отклонено: <b>{stats['rejected']}</b>\n\n"
            f"💰 Общий доход: <b>{stats['total_revenue_kzt']} ₸</b>"
        ) if not is_en else (
            f"📊 <b>PAYMENT STATISTICS</b>\n"
            f"════════════════════\n\n"
            f"📋 Total requests: <b>{stats['total']}</b>\n"
            f"⏳ Pending: <b>{stats['pending']}</b>\n"
            f"✅ Approved: <b>{stats['approved']}</b>\n"
            f"❌ Rejected: <b>{stats['rejected']}</b>\n\n"
            f"💰 Total revenue: <b>{stats['total_revenue_kzt']} ₸</b>"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=get_admin_kaspi_panel_keyboard(lang),
            parse_mode=ParseMode.HTML
        )
        
    elif data.startswith("admin_view_payment_"):
        payment_id = int(data.replace("admin_view_payment_", ""))
        admin_id = user.id
        
        # Delete original notification messages for this admin
        notifications = context.bot_data.get('admin_payment_notifications', {})
        if payment_id in notifications and admin_id in notifications[payment_id]:
            msg_ids = notifications[payment_id][admin_id]
            try:
                # Delete main notification
                await context.bot.delete_message(admin_id, msg_ids['message_id'])
            except Exception as e:
                print(f"Failed to delete notification: {e}")
            try:
                # Delete receipt photo
                await context.bot.delete_message(admin_id, msg_ids['photo_message_id'])
            except Exception as e:
                print(f"Failed to delete receipt photo: {e}")
            # Clean up
            del context.bot_data['admin_payment_notifications'][payment_id][admin_id]
        
        from database import get_kaspi_payment
        payment = await get_kaspi_payment(payment_id)
        if payment:
            # Send new message with payment details instead of editing
            await send_payment_details_to_admin(context, admin_id, payment, lang)
        else:
            await query.answer("❌ Заявка не найдена", show_alert=True)
        
    elif data.startswith("admin_approve_"):
        payment_id = int(data.replace("admin_approve_", ""))
        await process_payment_approval(update, context, payment_id, "", lang)
        
    elif data.startswith("admin_reject_"):
        payment_id = int(data.replace("admin_reject_", ""))
        # Store payment_id in context for comment input
        context.user_data['rejecting_payment'] = payment_id
        
        text = (
            "📝 Введи причину отклонения:\n"
            "(или напиши 'без комментария')"
        ) if not is_en else (
            "📝 Enter rejection reason:\n"
            "(or type 'no comment')"
        )
        
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        
    elif data.startswith("admin_approve_comment_"):
        payment_id = int(data.split("_")[-1])
        context.user_data['approving_payment'] = payment_id
        
        text = (
            "📝 Введи комментарий к одобрению:\n"
            "(или напиши 'ок')"
        ) if not is_en else (
            "📝 Enter approval comment:\n"
            "(or type 'ok')"
        )
        
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)


async def show_payment_to_admin(query, payment: dict, lang: str):
    """Show payment details to admin with action buttons."""
    from keyboards import get_admin_payment_action_keyboard
    
    status_map = {
        "pending": "⏳ Ожидает",
        "approved": "✅ Одобрено",
        "rejected": "❌ Отклонено"
    }
    
    text = (
        f"📋 <b>ЗАЯВКА #{payment['id']}</b>\n"
        f"════════════════════\n\n"
        f"👤 Пользователь: {payment['first_name']}\n"
        f"🆔 User ID: <code>{payment['user_id']}</code>\n"
        f"📦 Товар: <b>{payment['item_type']}</b>\n"
        f"🆔 Item ID: {payment['item_id']}\n"
        f"💰 Сумма: <b>{payment['amount_kzt']} ₸</b>\n"
        f"📊 Количество: <b>{payment['amount_item']}</b>\n"
        f"⏱ Статус: <b>{status_map.get(payment['status'], payment['status'])}</b>\n"
        f"🕐 Создано: {payment['created_at'][:16] if payment['created_at'] else '—'}"
    )
    
    # Always use edit_message_text to avoid caption errors
    await query.edit_message_text(
        text,
        reply_markup=get_admin_payment_action_keyboard(payment['id'], lang),
        parse_mode=ParseMode.HTML
    )
    
    # Store message ID for later deletion
    if 'payment_messages' not in context.user_data:
        context.user_data['payment_messages'] = {}
    context.user_data['payment_messages'][payment['id']] = query.message.message_id


async def send_payment_details_to_admin(context: ContextTypes.DEFAULT_TYPE, admin_id: int, 
                                           payment: dict, lang: str):
    """Send payment details and receipt photo to admin."""
    from keyboards import get_admin_payment_action_keyboard
    
    status_map = {
        "pending": "⏳ Ожидает",
        "approved": "✅ Одобрено",
        "rejected": "❌ Отклонено"
    }
    
    text = (
        f"📋 <b>ЗАЯВКА #{payment['id']}</b>\n"
        f"════════════════════\n\n"
        f"👤 Пользователь: {payment['first_name']}\n"
        f"🆔 User ID: <code>{payment['user_id']}</code>\n"
        f"📦 Товар: <b>{payment['item_type']}</b>\n"
        f"🆔 Item ID: {payment['item_id']}\n"
        f"💰 Сумма: <b>{payment['amount_kzt']} ₸</b>\n"
        f"📊 Количество: <b>{payment['amount_item']}</b>\n"
        f"⏱ Статус: <b>{status_map.get(payment['status'], payment['status'])}</b>\n"
        f"🕐 Создано: {payment['created_at'][:16] if payment['created_at'] else '—'}"
    )
    
    # Get receipt file_id if available
    receipt_file_id = context.bot_data.get('payment_receipts', {}).get(payment['id'])
    
    # Send receipt photo first if available and track its message ID
    photo_message_id = None
    if receipt_file_id:
        try:
            photo_msg = await context.bot.send_photo(
                admin_id,
                photo=receipt_file_id,
                caption=f"📄 Чек к заявке #{payment['id']}"
            )
            photo_message_id = photo_msg.message_id
        except Exception as e:
            print(f"Failed to send receipt photo: {e}")
    
    # Send new message with payment details
    msg = await context.bot.send_message(
        admin_id,
        text,
        reply_markup=get_admin_payment_action_keyboard(payment['id'], lang),
        parse_mode=ParseMode.HTML
    )
    
    # Store message IDs for later deletion
    if 'payment_messages' not in context.user_data:
        context.user_data['payment_messages'] = {}
    context.user_data['payment_messages'][payment['id']] = {
        'message_id': msg.message_id,
        'photo_message_id': photo_message_id
    }


async def process_payment_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                    payment_id: int, comment: str, lang: str):
    """Process payment approval and notify user."""
    from database import approve_kaspi_payment, get_kaspi_payment
    from config import ADMIN_IDS
    
    admin = update.effective_user
    result = await approve_kaspi_payment(payment_id, admin.id, comment)
    
    if not result:
        await update.effective_message.reply_text(
            "❌ Заявка не найдена или уже обработана" if lang != "en" else "❌ Payment not found or already processed"
        )
        return
    
    # Notify user about approval
    user_id = result['user_id']
    item_name = KASPI_PRICES.get(result['item_id'], {}).get("name", result['item_id'])
    
    try:
        text = (
            f"✅ <b>ПЛАТЕЖ ОДОБРЕН!</b>\n\n"
            f"Заявка #{payment_id}\n"
            f"📦 <b>{item_name}</b> начислено!\n\n"
            f"Спасибо за покупку! 🎉"
        ) if lang != "en" else (
            f"✅ <b>PAYMENT APPROVED!</b>\n\n"
            f"Payment #{payment_id}\n"
            f"📦 <b>{item_name}</b> credited!\n\n"
            f"Thank you for your purchase! 🎉"
        )
        
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Failed to notify user {user_id}: {e}")
    
    # Delete the payment message and receipt photo if tracked
    payment_messages = context.user_data.get('payment_messages', {})
    if payment_id in payment_messages:
        msg_data = payment_messages[payment_id]
        chat_id = update.effective_chat.id
        # Delete main payment message
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=msg_data['message_id']
            )
        except Exception as e:
            print(f"Failed to delete payment message: {e}")
        # Delete receipt photo if exists
        if msg_data.get('photo_message_id'):
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=msg_data['photo_message_id']
                )
            except Exception as e:
                print(f"Failed to delete receipt photo: {e}")
        del context.user_data['payment_messages'][payment_id]
    
    # Show confirmation and return to pending list
    from database import get_pending_payments
    pending = await get_pending_payments()
    
    if pending:
        text = (
            f"✅ <b>Заявка #{payment_id} одобрена!</b>\n\n"
            f"📋 Осталось заявок: <b>{len(pending)}</b>\n\n"
            f"Выберите следующую заявку:"
            if lang != "en" else
            f"✅ <b>Payment #{payment_id} approved!</b>\n\n"
            f"📋 Pending: <b>{len(pending)}</b>\n\n"
            f"Select next payment:"
        )
        from keyboards import get_admin_pending_list_keyboard
        await update.effective_message.reply_text(
            text,
            reply_markup=get_admin_pending_list_keyboard(pending, lang),
            parse_mode=ParseMode.HTML
        )
    else:
        await update.effective_message.reply_text(
            "✅ Все заявки обработаны!" if lang != "en" else "✅ All payments processed!",
            reply_markup=get_admin_kaspi_panel_keyboard(lang)
        )


async def process_payment_rejection(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                     payment_id: int, reason: str, lang: str):
    """Process payment rejection and notify user."""
    from database import reject_kaspi_payment, get_kaspi_payment
    
    admin = update.effective_user
    success = await reject_kaspi_payment(payment_id, admin.id, reason)
    
    if not success:
        await update.message.reply_text(
            "❌ Заявка не найдена или уже обработана" if lang != "en" else "❌ Payment not found or already processed"
        )
        return
    
    # Get payment info to notify user
    payment = await get_kaspi_payment(payment_id)
    user_id = payment['user_id']
    
    # Notify user about rejection
    user_notified = False
    try:
        text = (
            f"❌ <b>ПЛАТЕЖ ОТКЛОНЕН</b>\n\n"
            f"Заявка #{payment_id}\n\n"
            f"Причина: <b>{reason}</b>\n\n"
            f"Если есть вопросы — напиши @{SUPPORT_USERNAME or 'admin'}"
        ) if lang != "en" else (
            f"❌ <b>PAYMENT REJECTED</b>\n\n"
            f"Payment #{payment_id}\n\n"
            f"Reason: <b>{reason}</b>\n\n"
            f"If you have questions — contact @{SUPPORT_USERNAME or 'admin'}"
        )
        
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
        user_notified = True
        print(f"✅ User {user_id} notified about rejection of payment #{payment_id}")
    except Exception as e:
        print(f"❌ Failed to notify user {user_id} about rejection: {e}")
        import traceback
        traceback.print_exc()
    
    # Delete the payment message and receipt photo if tracked
    payment_messages = context.user_data.get('payment_messages', {})
    if payment_id in payment_messages:
        msg_data = payment_messages[payment_id]
        chat_id = update.effective_chat.id
        # Delete main payment message
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=msg_data['message_id']
            )
        except Exception as e:
            print(f"Failed to delete payment message: {e}")
        # Delete receipt photo if exists
        if msg_data.get('photo_message_id'):
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=msg_data['photo_message_id']
                )
            except Exception as e:
                print(f"Failed to delete receipt photo: {e}")
        del context.user_data['payment_messages'][payment_id]
    
    # Show confirmation and return to pending list
    from database import get_pending_payments
    pending = await get_pending_payments()
    
    if pending:
        # Build confirmation message with user notification status
        user_notification_status = (
            "✅ Пользователь уведомлен" if user_notified else "⚠️ Не удалось уведомить пользователя"
        ) if lang != "en" else (
            "✅ User notified" if user_notified else "⚠️ Failed to notify user"
        )
        
        text = (
            f"❌ <b>Заявка #{payment_id} отклонена!</b>\n"
            f"{user_notification_status}\n\n"
            f"📋 Осталось заявок: <b>{len(pending)}</b>\n\n"
            f"Выберите следующую заявку:"
            if lang != "en" else
            f"❌ <b>Payment #{payment_id} rejected!</b>\n"
            f"{user_notification_status}\n\n"
            f"📋 Pending: <b>{len(pending)}</b>\n\n"
            f"Select next payment:"
        )
        from keyboards import get_admin_pending_list_keyboard
        await update.message.reply_text(
            text,
            reply_markup=get_admin_pending_list_keyboard(pending, lang),
            parse_mode=ParseMode.HTML
        )
    else:
        user_notification_status = (
            "✅ Пользователь уведомлен" if user_notified else "⚠️ Не удалось уведомить пользователя"
        ) if lang != "en" else (
            "✅ User notified" if user_notified else "⚠️ Failed to notify user"
        )
        await update.message.reply_text(
            f"✅ Все заявки обработаны!\n{user_notification_status}" if lang != "en" 
            else f"✅ All payments processed!\n{user_notification_status}",
            reply_markup=get_admin_kaspi_panel_keyboard(lang)
        )


async def admin_kaspi_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin text input for payment comments."""
    user = update.effective_user
    
    # Check if user is admin
    from config import ADMIN_IDS
    if user.id not in ADMIN_IDS:
        return  # Ignore non-admin messages
    
    text = update.message.text
    lang = await _user_lang(user.id)
    
    # Check if admin is rejecting a payment
    if 'rejecting_payment' in context.user_data:
        payment_id = context.user_data.pop('rejecting_payment')
        await process_payment_rejection(update, context, payment_id, text, lang)
        return
    
    # Check if admin is approving with comment
    if 'approving_payment' in context.user_data:
        payment_id = context.user_data.pop('approving_payment')
        await process_payment_approval(update, context, payment_id, text, lang)
        return
