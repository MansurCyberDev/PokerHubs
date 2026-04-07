
# ==================== KASPI PAY HANDLERS ====================

# Kaspi payment prices mapping
KASPI_PRICES = {
    # Фишки
    "chips_10k": {"amount": 10000, "price_kzt": 500, "name": "10 000 фишек"},
    "chips_50k": {"amount": 50000, "price_kzt": 2000, "name": "50 000 фишек"},
    "chips_100k": {"amount": 100000, "price_kzt": 3500, "name": "100 000 фишек"},
    "chips_500k": {"amount": 500000, "price_kzt": 15000, "name": "500 000 фишек"},
    # Gold
    "gold_100": {"amount": 100, "price_kzt": 300, "name": "100 Gold"},
    "gold_500": {"amount": 500, "price_kzt": 1200, "name": "500 Gold"},
    "gold_1000": {"amount": 1000, "price_kzt": 2000, "name": "1000 Gold"},
    "gold_5000": {"amount": 5000, "price_kzt": 8500, "name": "5000 Gold"},
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

    # Map callback data to item info
    item_map = {
        "kaspi_chips_10k": ("chips", "chips_10k", 10000, 500),
        "kaspi_chips_50k": ("chips", "chips_50k", 50000, 2000),
        "kaspi_chips_100k": ("chips", "chips_100k", 100000, 3500),
        "kaspi_chips_500k": ("chips", "chips_500k", 500000, 15000),
        "kaspi_gold_100": ("gold", "gold_100", 100, 300),
        "kaspi_gold_500": ("gold", "gold_500", 500, 1200),
        "kaspi_gold_1000": ("gold", "gold_1000", 1000, 2000),
        "kaspi_gold_5000": ("gold", "gold_5000", 5000, 8500),
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
        
        # Notify admins about new payment
        await notify_admins_new_payment(context, payment_id, user, item_name, amount_kzt)
        
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
    
    # Notify admins about receipt
    await notify_admins_receipt_received(context, payment_id, user, file_id)


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
                                        user, receipt_file_id: str):
    """Notify admins that user uploaded receipt."""
    from config import ADMIN_IDS
    from keyboards import get_admin_payment_action_keyboard
    
    text = (
        f"📤 <b>ПОЛУЧЕН ЧЕК!</b>\n\n"
        f"Заявка: <code>#{payment_id}</code>\n"
        f"Пользователь: {user.first_name}\n"
        f"User ID: <code>{user.id}</code>\n\n"
        f"✅ Требуется проверка!"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            # Send receipt photo
            await context.bot.send_photo(
                admin_id,
                photo=receipt_file_id,
                caption=text,
                reply_markup=get_admin_payment_action_keyboard(payment_id),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Failed to send receipt to admin {admin_id}: {e}")


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
        # Show pending payments
        from database import get_pending_payments
        pending = await get_pending_payments()
        
        if not pending:
            await query.edit_message_text(
                "✅ Нет ожидающих заявок" if not is_en else "✅ No pending payments",
                reply_markup=get_admin_kaspi_panel_keyboard(lang)
            )
            return
        
        # Show first pending payment
        payment = pending[0]
        await show_payment_to_admin(query, payment, lang)
        
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
        payment_id = int(data.replace("admin_approve_comment_", ""))
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
    
    if payment.get('receipt_photo_id'):
        # Show receipt photo with details
        await query.edit_message_caption(
            caption=text,
            reply_markup=get_admin_payment_action_keyboard(payment['id'], lang),
            parse_mode=ParseMode.HTML
        )
    else:
        await query.edit_message_text(
            text,
            reply_markup=get_admin_payment_action_keyboard(payment['id'], lang),
            parse_mode=ParseMode.HTML
        )


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
    
    # Show next pending or stats
    from database import get_pending_payments
    pending = await get_pending_payments()
    
    if pending:
        await show_payment_to_admin(update.callback_query, pending[0], lang)
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
    except Exception as e:
        print(f"Failed to notify user {user_id}: {e}")
    
    await update.message.reply_text(
        f"✅ Заявка #{payment_id} отклонена" if lang != "en" else f"✅ Payment #{payment_id} rejected",
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
