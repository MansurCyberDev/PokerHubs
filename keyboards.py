from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Dict


def get_main_menu_keyboard(bot_username: str = "", lang: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню в ЛС бота."""
    add_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🎰 " + ("Daily Bonus" if is_en else "Ежедневный бонус"), callback_data="daily_bonus")],
        [InlineKeyboardButton("👤 " + ("My Profile" if is_en else "Мой профиль"), callback_data="menu_profile")],
        [InlineKeyboardButton("🌐 " + ("Language" if is_en else "Язык"), callback_data="menu_language")],
        [InlineKeyboardButton("🏆 " + ("Top Players" if is_en else "Топ игроков"), callback_data="menu_top")],
        [InlineKeyboardButton("➕ " + ("Add to Group" if is_en else "Добавить в группу"), url=add_url)],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_profile_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("💰 " + ("Get Free Chips" if is_en else "Бесплатные фишки"), callback_data="menu_chips")],
        [InlineKeyboardButton("🎒 Inventory" if is_en else "🎒 Инвентарь", callback_data="menu_inventory")],
    ]
    # Add dynamic back button if provided, otherwise default to main menu
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_shop_categories_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Выбор категории скинов."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🃏 " + ("Card Skins" if is_en else "Скины карт"), callback_data="shop_category_cards")],
        [InlineKeyboardButton("🎰 " + ("Table Skins" if is_en else "Скины столов"), callback_data="shop_category_tables")],
        [InlineKeyboardButton("🪙 " + ("Chips" if is_en else "Фишки"), callback_data="shop_category_chips")],
        [InlineKeyboardButton("💎 " + ("Buy Gold (Kaspi)" if is_en else "Купить золото (Kaspi)"), callback_data="shop_gold_buy")],
    ]
    # Add dynamic back button if provided, otherwise default to main menu
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_shop_keyboard(owned_skins: list, current_skin: str, lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Список скинов карт в магазине."""
    from skins import SKINS
    is_en = lang == "en"
    keyboard = []
    for skin_id, skin in SKINS.items():
        if skin_id in owned_skins:
            if skin_id == current_skin:
                status_icon = "✨"
                label = f"{status_icon} {skin['name']} ({'equipped' if is_en else 'надето'})"
            else:
                status_icon = "✅"
                label = f"{status_icon} {skin['name']} ({'owned' if is_en else 'в инвентаре'})"
            cb = f"shop_equip_{skin_id}"
        else:
            label = f"🔒 {skin['name']} — {skin['price']} 🪙"
            cb = f"shop_buy_{skin_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb)])
    # Add dynamic back button if provided, otherwise default to shop categories
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_shop")])
    return InlineKeyboardMarkup(keyboard)


def get_table_skins_keyboard(owned_skins: list, current_skin: str, lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Список скинов столов в магазине."""
    from skins import TABLE_SKINS
    is_en = lang == "en"
    keyboard = []
    for skin_id, skin in TABLE_SKINS.items():
        if skin_id in owned_skins:
            if skin_id == current_skin:
                status_icon = "✨"
                label = f"{status_icon} {skin['name']} ({'equipped' if is_en else 'надето'})"
            else:
                status_icon = "✅"
                label = f"{status_icon} {skin['name']} ({'owned' if is_en else 'в инвентаре'})"
            cb = f"table_equip_{skin_id}"
        else:
            label = f"🔒 {skin['name']} — {skin['price']} 🪙"
            cb = f"table_buy_{skin_id}"
        keyboard.append([InlineKeyboardButton(label, callback_data=cb)])
    # Add dynamic back button if provided, otherwise default to shop categories
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_shop")])
    return InlineKeyboardMarkup(keyboard)


def get_inventory_categories_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Inventory categories - only cards and tables."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🃏 " + ("Card Decks" if is_en else "Колоды карт"), callback_data="inv_category_cards")],
        [InlineKeyboardButton("🎰 " + ("Table Skins" if is_en else "Скины столов"), callback_data="inv_category_tables")],
    ]
    # Add dynamic back button if provided, otherwise default to profile
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_profile")])
    return InlineKeyboardMarkup(keyboard)


def get_gold_packages_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Пакеты для покупки золота (Telegram Stars)."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("💎 50 💰 — 25 ⭐", callback_data="gold_buy_50")],
        [InlineKeyboardButton("💎 150 💰 — 69 ⭐", callback_data="gold_buy_150")],
        [InlineKeyboardButton("💎 500 💰 — 199 ⭐", callback_data="gold_buy_500")],
        [InlineKeyboardButton("💎 1200 💰 — 449 ⭐ 🔥", callback_data="gold_buy_1200")],
    ]
    # Add dynamic back button if provided, otherwise default to profile
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_profile")])
    return InlineKeyboardMarkup(keyboard)


def get_chips_packages_keyboard(lang: str = "ru", back_button: InlineKeyboardButton = None) -> InlineKeyboardMarkup:
    """Пакеты для получения фишек через рекламу и покупки."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("📺 " + ("Watch Ad — 3000 chips" if is_en else "Смотреть рекламу — 3000 фишек"), callback_data="chips_watch_ad")],
        [InlineKeyboardButton("💳 " + ("Buy with Kaspi" if is_en else "Купить через Kaspi"), callback_data="kaspi_chips_menu")],
    ]
    # Add dynamic back button if provided, otherwise default to profile
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_profile")])
    return InlineKeyboardMarkup(keyboard)


def get_language_keyboard(back_button: InlineKeyboardButton = None, lang: str = "ru") -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ]
    # Add dynamic back button if provided, otherwise default to main menu
    if back_button:
        keyboard.append([back_button])
    else:
        keyboard.append([InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_registration_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🪑 " + "Сесть за стол", callback_data="join_game")],
        [
            InlineKeyboardButton("🎮 " + "Начать игру", callback_data="start_early")
        ],
        [
            InlineKeyboardButton("⚙️ " + "Блайнды", callback_data="set_blinds"),
            InlineKeyboardButton("👥 " + "Места", callback_data="set_seats")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_blinds_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🎯 " + "10/20", callback_data="blind_10_20")],
        [InlineKeyboardButton("🎯 " + "25/50", callback_data="blind_25_50")],
        [InlineKeyboardButton("🎯 " + "50/100", callback_data="blind_50_100")],
        [InlineKeyboardButton("🎯 " + "100/200", callback_data="blind_100_200")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_seats_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("👥 " + "2 игрока", callback_data="seats_2")],
        [InlineKeyboardButton("👥 " + "4 игрока", callback_data="seats_4")],
        [InlineKeyboardButton("👥 " + "6 игроков", callback_data="seats_6")],
        [InlineKeyboardButton("👥 " + "9 игроков", callback_data="seats_9")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_play_again_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔄 " + "Сыграть еще раз", callback_data="new_game_dm")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_private_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("👤 Профиль"), KeyboardButton("🛍️ Магазин")],
        [KeyboardButton("🌐 Язык"), KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_turn_reply_keyboard(options: List[str], lang: str = "ru") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = []
    
    # Основные действия - первая строка
    primary_actions = []
    if "check" in options:
        primary_actions.append(KeyboardButton("✅ " + ("Check" if is_en else "Чек")))
    if "call" in options:
        primary_actions.append(KeyboardButton("📞 " + ("Call" if is_en else "Колл")))
    if "fold" in options:
        primary_actions.append(KeyboardButton("❌ " + ("Fold" if is_en else "Фолд")))
    
    if primary_actions:
        keyboard.append(primary_actions)

    # Второстепенные действия - вторая строка
    secondary_actions = []
    if "bet" in options:
        secondary_actions.append(KeyboardButton("💰 " + ("Bet" if is_en else "Ставка")))
    if "raise" in options:
        secondary_actions.append(KeyboardButton("📈 " + ("Raise" if is_en else "Рейз")))
    if "all_in" in options:
        secondary_actions.append(KeyboardButton("🔥 " + ("All-in" if is_en else "All-in")))
        
    if secondary_actions:
        keyboard.append(secondary_actions)

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_game_keyboard(options: List[str]) -> InlineKeyboardMarkup:
    keyboard = []
    row = []

    if "check" in options:
        row.append(InlineKeyboardButton("✅ Чек", callback_data="action_check"))
    if "call" in options:
        row.append(InlineKeyboardButton("📞 Колл", callback_data="action_call"))
    if "fold" in options:
        row.append(InlineKeyboardButton("❌ Фолд", callback_data="action_fold"))

    if row:
        keyboard.append(row)

    row2 = []
    if "bet" in options:
        row2.append(InlineKeyboardButton("💰 Ставка", callback_data="action_bet"))
    if "raise" in options:
        row2.append(InlineKeyboardButton("📈 Рейз", callback_data="action_raise"))
    if "all_in" in options:
        row2.append(InlineKeyboardButton("🔥 All-in", callback_data="action_all_in"))

    if row2:
        keyboard.append(row2)

    return InlineKeyboardMarkup(keyboard)


def get_bet_amounts_keyboard(current_bet: int, min_raise: int, player_stack: int, pot: int, lang: str = "ru") -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = []
    
    # Если стек меньше минимального рейза - только All-in
    if player_stack < min_raise:
        if player_stack > 0:
            keyboard.append([InlineKeyboardButton(
                f"🔥 All-in ({player_stack})", 
                callback_data=f"bet_amount_{player_stack}"
            )])
        keyboard.append([
            InlineKeyboardButton("✏️ " + ("Custom" if is_en else "Своя сумма"), callback_data="action_custom_hint"),
            InlineKeyboardButton("🔙 " + ("Cancel" if is_en else "Отмена"), callback_data="action_cancel")
        ])
        return InlineKeyboardMarkup(keyboard)
    
    # Предложенные ставки - первая строка
    pot_suggestions = [
        ("½ " + ("Pot" if is_en else "Банка"), pot // 2),
        ("¾ " + ("Pot" if is_en else "Банка"), int(pot * 0.75)),
        ("1x " + ("Pot" if is_en else "Банк"), pot),
    ]
    
    pot_row = []
    for label, amount in pot_suggestions:
        # Для bet (current_bet=0): amount - это target_total
        # Для raise (current_bet>0): amount должен быть >= current_bet + min_raise
        min_target = min_raise if current_bet == 0 else current_bet + min_raise
        if amount >= min_target and amount <= player_stack:
            pot_row.append(InlineKeyboardButton(f"{label} ({amount})", callback_data=f"bet_amount_{amount}"))
    
    if pot_row:
        keyboard.append(pot_row)
    
    # Множители рейза - вторая строка
    raise_multipliers = [
        ("2x " + ("Raise" if is_en else "Рейз"), min_raise * 2),
        ("3x " + ("Raise" if is_en else "Рейз"), min_raise * 3),
    ]
    
    raise_row = []
    for label, amount in raise_multipliers:
        min_target = min_raise if current_bet == 0 else current_bet + min_raise
        if amount >= min_target and amount <= player_stack:
            raise_row.append(InlineKeyboardButton(f"{label} ({amount})", callback_data=f"bet_amount_{amount}"))
    
    if raise_row:
        keyboard.append(raise_row)
    
    # Фиксированные суммы - третья строка
    fixed_amounts = []
    for amount in [min_raise, min_raise * 2, player_stack]:
        min_target = min_raise if current_bet == 0 else current_bet + min_raise
        if amount >= min_target and amount <= player_stack and amount not in [a for _, a in pot_suggestions + raise_multipliers]:
            fixed_amounts.append(InlineKeyboardButton(f"{amount} 💰", callback_data=f"bet_amount_{amount}"))
    
    if fixed_amounts:
        keyboard.append(fixed_amounts)

    # Кнопки управления - четвертая строка
    control_row = [
        InlineKeyboardButton("✏️ " + ("Custom" if is_en else "Своя сумма"), callback_data="action_custom_hint"),
        InlineKeyboardButton("🔙 " + ("Cancel" if is_en else "Отмена"), callback_data="action_cancel")
    ]
    keyboard.append(control_row)
    
    return InlineKeyboardMarkup(keyboard)


# ==================== KASPI PAY KEYBOARDS ====================

def get_kaspi_chips_packages_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Пакеты фишек для покупки через Kaspi Pay."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(f"🪙 10 000 {'chips' if is_en else 'фишек'} — 500 ₸", callback_data="kaspi_chips_10k")],
        [InlineKeyboardButton(f"🪙 50 000 {'chips' if is_en else 'фишек'} — 2 000 ₸", callback_data="kaspi_chips_50k")],
        [InlineKeyboardButton(f"🪙 100 000 {'chips' if is_en else 'фишек'} — 3 500 ₸", callback_data="kaspi_chips_100k")],
        [InlineKeyboardButton(f"🪙 500 000 {'chips' if is_en else 'фишек'} — 15 000 ₸ 🔥", callback_data="kaspi_chips_500k")],
        [InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="shop_category_chips")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_kaspi_gold_packages_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Пакеты Gold для покупки через Kaspi Pay."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton("💎 100 Gold — 100 ₸", callback_data="kaspi_gold_100")],
        [InlineKeyboardButton("💎 200 Gold — 150 ₸", callback_data="kaspi_gold_200")],
        [InlineKeyboardButton("💎 300 Gold — 200 ₸", callback_data="kaspi_gold_300")],
        [InlineKeyboardButton("💎 500 Gold — 300 ₸ (выгода 100₸)", callback_data="kaspi_gold_500")],
        [InlineKeyboardButton("💎 1000 Gold — 550 ₸ (выгода 450₸)", callback_data="kaspi_gold_1000")],
        [InlineKeyboardButton("💎 2000 Gold — 1000 ₸ (выгода 1000₸) 🔥", callback_data="kaspi_gold_2000")],
        [InlineKeyboardButton("� " + ("Back" if is_en else "Назад"), callback_data="menu_shop")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== GOLD EXCHANGE FOR CHIPS ====================

# Exchange rates: Gold -> Chips
GOLD_EXCHANGE_RATES = {
    "gold_exchange_100": {"gold_cost": 100, "chips": 1000, "bonus": "+0%"},
    "gold_exchange_200": {"gold_cost": 200, "chips": 2500, "bonus": "+25% выгода"},
    "gold_exchange_300": {"gold_cost": 300, "chips": 4000, "bonus": "+33% выгода 🔥"},
    "gold_exchange_500": {"gold_cost": 500, "chips": 7500, "bonus": "+50% выгода 💎"},
}

def get_gold_exchange_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура обмена золота на фишки."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(f"🪙 100 Gold → 1,000 фишек", callback_data="gold_exchange_100")],
        [InlineKeyboardButton(f"🪙 200 Gold → 2,500 фишек (+25%)", callback_data="gold_exchange_200")],
        [InlineKeyboardButton(f"🪙 300 Gold → 4,000 фишек (+33%) 🔥", callback_data="gold_exchange_300")],
        [InlineKeyboardButton(f"🪙 500 Gold → 7,500 фишек (+50%) 💎", callback_data="gold_exchange_500")],
        [InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_shop")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_kaspi_payment_instruction_keyboard(payment_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для инструкции по оплате (после создания заявки)."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "📤 " + ("I paid - Send receipt" if is_en else "Я оплатил - Отправить чек"), 
            callback_data=f"kaspi_upload_{payment_id}"
        )],
        [InlineKeyboardButton(
            "❌ " + ("Cancel payment" if is_en else "Отменить заявку"), 
            callback_data=f"kaspi_cancel_{payment_id}"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_kaspi_receipt_upload_keyboard(payment_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для загрузки чека."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "📎 " + ("Send receipt photo" if is_en else "Отправить фото чека"), 
            callback_data=f"kaspi_receipt_{payment_id}"
        )],
        [InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_requests_panel_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Админ-панель заявок (платежи + обращения)."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "💳 " + ("Kaspi payments" if is_en else "Kaspi платежи"),
            callback_data="admin_kaspi_pending"
        )],
        [InlineKeyboardButton(
            "📝 " + ("User issues" if is_en else "Обращения пользователей"),
            callback_data="admin_issues"
        )],
        [InlineKeyboardButton("🔙 " + ("Back" if is_en else "Назад"), callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_payment_view_keyboard(payment_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для просмотра деталей заявки админом."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "📋 " + ("View details" if is_en else "Посмотреть заявку"),
            callback_data=f"admin_view_payment_{payment_id}"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_pending_list_keyboard(pending_payments: list, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура списка заявок для админа с отображением статуса."""
    is_en = lang == "en"
    keyboard = []
    
    status_emoji = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌'
    }
    
    for payment in pending_payments:
        payment_id = payment['id']
        status = payment.get('status', 'pending')
        item_name = payment.get('item_id', 'Unknown')
        amount_kzt = payment.get('amount_kzt', 0)
        user_name = payment.get('first_name', 'Unknown')
        emoji = status_emoji.get(status, '⏳')
        
        # Mark reviewed payments with different style
        if status in ['approved', 'rejected']:
            label = f"{emoji} #{payment_id} ✓ {item_name} ({amount_kzt}₸) — {user_name}"
        else:
            label = f"{emoji} #{payment_id} {item_name} ({amount_kzt}₸) — {user_name}"
        
        keyboard.append([InlineKeyboardButton(
            label,
            callback_data=f"admin_view_payment_{payment_id}"
        )])
    
    # Add back button
    keyboard.append([InlineKeyboardButton(
        "🔙 " + ("Back to admin panel" if is_en else "Назад в админ панель"),
        callback_data="menu_admin"
    )])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_payment_action_keyboard(payment_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий для админа над конкретной заявкой."""
    is_en = lang == "en"
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ " + ("Approve" if is_en else "Одобрить"),
                callback_data=f"admin_approve_{payment_id}"
            ),
            InlineKeyboardButton(
                "❌ " + ("Reject" if is_en else "Отклонить"),
                callback_data=f"admin_reject_{payment_id}"
            ),
        ],

        [InlineKeyboardButton(
            "📋 " + ("Back to list" if is_en else "Назад к списку"),
            callback_data="admin_kaspi_pending"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== ADMIN ISSUES KEYBOARDS ====================

def get_admin_issues_panel_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Главная клавиатура панели обращений (Issues)."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "📝 " + ("Pending Issues" if is_en else "Ожидающие обращения"),
            callback_data="admin_issues_pending"
        )],
        [InlineKeyboardButton(
            "📊 " + ("Statistics" if is_en else "Статистика"),
            callback_data="admin_issues_stats"
        )],
        [InlineKeyboardButton(
            "🔙 " + ("Back to Admin" if is_en else "Назад к админке"),
            callback_data="menu_admin"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_issue_view_keyboard(issue_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для просмотра обращения с кнопкой ответа."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "💬 " + ("Reply" if is_en else "Ответить"),
            callback_data=f"admin_reply_issue_{issue_id}"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_issue_action_keyboard(issue_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий над обращением (после просмотра)."""
    is_en = lang == "en"
    keyboard = [
        [InlineKeyboardButton(
            "💬 " + ("Reply" if is_en else "Ответить"),
            callback_data=f"admin_reply_issue_{issue_id}"
        )],
        [InlineKeyboardButton(
            "📋 " + ("Back to list" if is_en else "Назад к списку"),
            callback_data="admin_issues_pending"
        )],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_pending_issues_keyboard(pending_issues: List[Dict], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура со списком ожидающих обращений."""
    is_en = lang == "en"
    keyboard = []
    
    for issue in pending_issues:
        issue_id = issue['id']
        user_name = issue.get('first_name', 'Unknown')
        preview = issue.get('message', '')[:30]
        
        keyboard.append([InlineKeyboardButton(
            f"📝 #{issue_id} — {user_name}: {preview}...",
            callback_data=f"admin_view_issue_{issue_id}"
        )])
    
    # Add back button
    keyboard.append([InlineKeyboardButton(
        "🔙 " + ("Back to issues" if is_en else "Назад к обращениям"),
        callback_data="admin_issues"
    )])
    
    return InlineKeyboardMarkup(keyboard)
